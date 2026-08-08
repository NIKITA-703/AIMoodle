import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from selenium import webdriver
from selenium.common.exceptions import WebDriverException

from app.ai_utils import check_ai_ready, clean_html_to_text, is_context_error_text, save_text_file
from app.auth import login_on_mudl
from app.config import (
    AUTO_USE_LAST_ATTEMPT,
    PARALLEL_WORKERS,
    REQUIRE_LECTURE_CONTEXT,
    TESTS_LIMIT,
    options,
    url_home_page,
    url_login,
)
from app.flows.course_flow import (
    find_current_test_info,
    get_active_course_links,
    get_current_course_link,
)
from app.flows.lecture_flow import (
    find_lecture_urls,
    is_final_test,
    load_saved_course_context,
    save_page_html,
    try_get_lecture_via_breadcrumbs,
)
from app.flows.test_flow import (
    collect_previous_attempt_review,
    get_quiz_requirements,
    has_current_attempt,
    solve_active_test,
    start_test_attempt,
)
from app.models import QuizResult
from app.stats import finish_run, format_duration, get_global_stats, record_attempt, start_run


_DRIVER_CREATION_LOCK = threading.Lock()


@dataclass(frozen=True)
class CourseAssignment:
    course_url: str
    course_name: str
    test_name: str
    test_url: str
    topic_name: str | None = None


@dataclass
class WorkerOutcome:
    worker_id: int
    course_name: str
    submitted: int = 0
    passed: int = 0
    errors: int = 0
    message: str = ""


@dataclass
class AttemptBudget:
    limit: int
    claimed: int = 0
    submitted: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def reserve(self):
        with self._lock:
            if self.claimed >= self.limit:
                return False
            self.claimed += 1
            return True

    def complete(self, submitted):
        with self._lock:
            if submitted:
                self.submitted += 1
            else:
                self.claimed = max(0, self.claimed - 1)


def run(tests_limit=None, parallel_workers=None):
    driver = None
    run_id = None
    ignored_courses = set()
    ignored_tests = set()
    passed_this_run = 0
    submitted_attempts_this_run = 0
    errors_count = 0
    # Maximum number of quiz attempts submitted to Moodle during this run.
    tests_limit = TESTS_LIMIT if tests_limit is None else max(1, int(tests_limit))
    parallel_workers = (
        PARALLEL_WORKERS
        if parallel_workers is None
        else min(4, max(1, int(parallel_workers)))
    )
    start_time_total = time.time()

    stats = get_global_stats()
    _print_start_stats(stats)
    print(
        f"⚙️ Режим: worker={parallel_workers}, "
        f"общий лимит отправленных попыток={tests_limit}.\n"
    )

    ai_ready, ai_message = check_ai_ready()
    if not ai_ready:
        print(f"❌ {ai_message}")
        print("⛔ Запуск остановлен. Сначала включи LM Studio и загрузи модель.\n")
        return
    print(f"🧠 {ai_message}\n")

    run_id = start_run()

    try:
        driver = _create_driver()
        if not _open_authenticated_home(driver):
            return

        try:
            print("Используемый User-Agent:", driver.execute_script("return navigator.userAgent;"), "\n")
        except Exception:
            pass

        if parallel_workers > 1:
            worker_limit = min(parallel_workers, tests_limit)
            assignments = _discover_course_assignments(driver, worker_limit)
            if not assignments:
                print("🎉 Не найдено доступных тестов для параллельного запуска.")
                return

            driver.quit()
            driver = None
            outcomes = _run_parallel_workers(assignments, run_id, tests_limit)
            submitted_attempts_this_run = sum(item.submitted for item in outcomes)
            passed_this_run = sum(item.passed for item in outcomes)
            errors_count += sum(item.errors for item in outcomes)
            print(
                f"\n🏁 Параллельный запуск завершён: отправлено "
                f"{submitted_attempts_this_run}/{tests_limit}, "
                f"успешно {passed_this_run}."
            )
            return

        while submitted_attempts_this_run < tests_limit:
            print(f"\n🔎 Ищем активный курс (пропущено: {len(ignored_courses)})...\n")
            course_url, course_name = get_current_course_link(driver, ignore_urls=ignored_courses)

            if not course_url:
                print("🎉 Все доступные курсы обработаны.")
                break

            print(f"📘 Заходим в: {course_name}\n")
            driver.get(course_url)
            test_name, test_url, topic_name = find_current_test_info(
                driver,
                ignore_test_urls=ignored_tests,
            )

            if not test_name or not test_url:
                print(f"⚠️ В курсе '{course_name}' нет доступных тестов для этой сессии.")
                ignored_courses.add(course_url)
                driver.get(url_home_page)
                time.sleep(2)
                continue

            course_id = _query_id(course_url)
            quiz_id = _query_id(test_url)
            print(f"📝 Активный тест: {test_name}\n")

            lecture_text = _load_lecture_text(
                driver,
                course_name,
                test_name,
                topic_name,
            )

            driver.get(test_url)
            requirements = get_quiz_requirements(driver, course_id=course_id, quiz_id=quiz_id)
            _print_requirements(requirements)
            previous_review = collect_previous_attempt_review(
                driver,
                course_name=course_name,
                test_name=test_name,
                requirements=requirements,
            )
            if previous_review and previous_review.get("new_confirmed_count", 0):
                print(
                    f"🧠 Из прошлой попытки получено новых "
                    f"подтверждённых ответов: {previous_review['new_confirmed_count']}"
                )

            if not lecture_text:
                print("⚠️ Лекция не найдена на главной. Пробуем через навигацию теста...")
                lecture_text = try_get_lecture_via_breadcrumbs(driver, course_name) or ""
                if is_context_error_text(lecture_text):
                    print(f"⚠️ План Б не смог извлечь текст лекции: {lecture_text}")
                    lecture_text = ""
                if driver.current_url != test_url:
                    driver.get(test_url)

            if not lecture_text and is_final_test(test_name, topic_name):
                print("📚 Итоговый тест: загружаем сохранённые лекции всего курса...")
                lecture_text = load_saved_course_context(course_name)

            if lecture_text:
                print(f"🧠 Контекст лекции подготовлен: {len(lecture_text)} символов.")
            else:
                print("🤷 Лекция отсутствует. Ответы будут помечены как общие знания.")

            if not lecture_text and REQUIRE_LECTURE_CONTEXT and not has_current_attempt(driver):
                print(
                    "🛑 Новый тест не запускаем: не удалось подготовить "
                    "проверенный контекст лекции."
                )
                ignored_tests.add(test_url)
                driver.get(url_home_page)
                continue
            if not lecture_text and REQUIRE_LECTURE_CONTEXT:
                print(
                    "⚠️ Попытка уже запущена, поэтому продолжаем без лекции, "
                    "чтобы Moodle не отправил её по таймеру."
                )

            is_last_retry = (
                requirements.allowed_attempts is not None
                and requirements.attempt_number is not None
                and requirements.attempt_number > 1
                and requirements.attempt_number >= requirements.allowed_attempts
                and not has_current_attempt(driver)
            )
            if is_last_retry and not AUTO_USE_LAST_ATTEMPT:
                print(
                    "🛑 Осталась последняя повторная попытка. "
                    "Автозапуск заблокирован; ответы из обзора уже сохранены. "
                    "Запуск бота остановлен."
                )
                break

            if not start_test_attempt(driver):
                ignored_tests.add(test_url)
                errors_count += 1
                driver.get(url_home_page)
                continue

            attempt_started_at = datetime.now().isoformat(timespec="seconds")
            attempt_start = time.time()
            result = solve_active_test(
                driver,
                lecture_text,
                course_name=course_name,
                test_name=test_name,
                requirements=requirements,
            )
            duration = time.time() - attempt_start
            record_attempt(
                run_id,
                course_name,
                test_name,
                result,
                duration_sec=duration,
                started_at=attempt_started_at,
            )

            if result.submitted:
                submitted_attempts_this_run += 1
                print(
                    f"📝 Отправлено попыток за запуск: "
                    f"{submitted_attempts_this_run}/{tests_limit}"
                )

            stop_requested = False
            if result.passed:
                passed_this_run += 1
                print(f"✅ Успешно пройдено за запуск: {passed_this_run}")
            else:
                stop_requested = _handle_failed_result(result, test_url, ignored_tests)
                if result.error:
                    errors_count += 1

            if stop_requested:
                print("⏸️ Запуск остановлен: последняя попытка требует ручного решения.")
                break

            print("🔙 На главную...")
            driver.get(url_home_page)
            time.sleep(2)

    except KeyboardInterrupt:
        print("\n⏹️ Работа остановлена пользователем.")
    except Exception as e:
        errors_count += 1
        print(f"\n💀 GLOBAL ERROR: {e}")
    finally:
        duration = time.time() - start_time_total
        if run_id:
            finish_run(run_id, duration, errors_count=errors_count)
        print(f"\n⏱️ ОБЩЕЕ ВРЕМЯ РАБОТЫ: {format_duration(duration)}\n")

        if driver:
            try:
                driver.quit()
                print("Browser CLOSED")
            except Exception as e:
                print(f"⚠️ Не удалось корректно закрыть браузер: {e}")


def _open_authenticated_home(driver):
    driver.get(url_home_page)
    time.sleep(5)
    driver.refresh()
    time.sleep(3)

    if driver.current_url.startswith(url_login):
        if not login_on_mudl(driver):
            print("Не удалось попасть в ЛК.")
            return False
        print("Авторизация прошла успешно!\n")
        time.sleep(5)
    else:
        print("Личный кабинет открыт:", driver.current_url)

    return True


def _discover_course_assignments(driver, limit):
    """Find at most one available quiz in each distinct active course."""
    driver.get(url_home_page)
    courses = get_active_course_links(driver)
    assignments = []

    print(f"🧭 Координатор проверяет курсы для {limit} worker...")
    for course_url, course_name, state_text in courses:
        print(f"🔎 Проверяем курс: {course_name} ({state_text})")
        try:
            driver.get(course_url)
            test_name, test_url, topic_name = find_current_test_info(driver)
        except Exception as e:
            print(f"⚠️ Не удалось проверить курс '{course_name}': {e}")
            continue

        if not test_name or not test_url:
            print(f"⏭️ В курсе '{course_name}' нет доступных тестов.")
            continue

        assignments.append(
            CourseAssignment(
                course_url=course_url,
                course_name=course_name,
                test_name=test_name,
                test_url=test_url,
                topic_name=topic_name,
            )
        )
        print(f"📌 Назначено: {course_name} -> {test_name}")
        if len(assignments) >= limit:
            break

    return assignments


def _run_parallel_workers(assignments, run_id, tests_limit=None):
    budget = AttemptBudget(tests_limit or len(assignments))
    print(
        f"\n⚙️ Запускаем {len(assignments)} worker: "
        f"отдельный Chrome на курс, общий лимит {budget.limit} попыток."
    )
    outcomes = []
    with ThreadPoolExecutor(
        max_workers=len(assignments),
        thread_name_prefix="course-worker",
    ) as executor:
        futures = {
            executor.submit(_course_worker, index, assignment, run_id, budget): assignment
            for index, assignment in enumerate(assignments, start=1)
        }
        for future in as_completed(futures):
            assignment = futures[future]
            try:
                outcome = future.result()
            except BaseException as e:
                print(f"💀 Worker курса '{assignment.course_name}' завершился с ошибкой: {e}")
                outcome = WorkerOutcome(
                    worker_id=0,
                    course_name=assignment.course_name,
                    errors=1,
                    message=str(e),
                )
            outcomes.append(outcome)
            print(
                f"🏁 Worker {outcome.worker_id} ({outcome.course_name}): "
                f"отправлено {outcome.submitted}, успешно {outcome.passed}."
            )

    return outcomes


def _course_worker(worker_id, assignment, run_id, budget):
    outcome = WorkerOutcome(worker_id=worker_id, course_name=assignment.course_name)
    driver = None
    prefix = f"[W{worker_id}]"

    try:
        print(f"{prefix} Запускаем Chrome для курса '{assignment.course_name}'.")
        # Selenium Manager and its cache are shared, so only driver creation is serialized.
        with _DRIVER_CREATION_LOCK:
            driver = _create_driver()

        if not _open_authenticated_home(driver):
            outcome.errors = 1
            outcome.message = "Не удалось авторизоваться"
            return outcome

        current_assignment = assignment
        ignored_tests = set()
        lecture_text = None

        while current_assignment and budget.reserve():
            print(f"{prefix} Открываем тест: {current_assignment.test_name}")
            result, lecture_text = _execute_assigned_attempt(
                driver,
                current_assignment,
                run_id,
                prefix,
                lecture_text=lecture_text,
            )
            budget.complete(result.submitted)
            outcome.submitted += int(result.submitted)
            outcome.passed += int(result.passed)
            outcome.errors += int(bool(result.error))
            outcome.message = result.error

            if result.submitted and not result.passed and _can_retry_result(result):
                print(
                    f"{prefix} 🔁 Балл ниже проходного. Повторяем этот тест "
                    "с ответами из обзора."
                )
                continue

            ignored_tests.add(current_assignment.test_url)
            current_assignment = _find_next_course_assignment(
                driver,
                current_assignment,
                ignored_tests,
            )
            lecture_text = None

        return outcome
    except KeyboardInterrupt:
        outcome.errors = 1
        outcome.message = "Остановлено пользователем"
        return outcome
    except Exception as e:
        outcome.errors = 1
        outcome.message = str(e)
        print(f"{prefix} 💀 Ошибка worker: {e}")
        return outcome
    finally:
        if driver:
            try:
                driver.quit()
                print(f"{prefix} Browser CLOSED")
            except BaseException as e:
                print(f"{prefix} ⚠️ Не удалось закрыть браузер: {e}")


def _execute_assigned_attempt(driver, assignment, run_id, prefix, lecture_text=None):
    course_id = _query_id(assignment.course_url)
    quiz_id = _query_id(assignment.test_url)
    if lecture_text is None:
        driver.get(assignment.course_url)
        lecture_text = _load_lecture_text(
            driver,
            assignment.course_name,
            assignment.test_name,
            assignment.topic_name,
        )

    driver.get(assignment.test_url)
    requirements = get_quiz_requirements(driver, course_id=course_id, quiz_id=quiz_id)
    _print_requirements(requirements)
    previous_review = collect_previous_attempt_review(
        driver,
        course_name=assignment.course_name,
        test_name=assignment.test_name,
        requirements=requirements,
    )
    if previous_review and previous_review.get("new_confirmed_count", 0):
        print(
            f"{prefix} 🧠 Из прошлых попыток получено новых подтверждённых "
            f"ответов: {previous_review['new_confirmed_count']}"
        )

    if not lecture_text:
        print(f"{prefix} ⚠️ Пробуем найти лекцию через навигацию теста...")
        lecture_text = try_get_lecture_via_breadcrumbs(driver, assignment.course_name) or ""
        if is_context_error_text(lecture_text):
            print(f"{prefix} ⚠️ Не удалось извлечь текст лекции: {lecture_text}")
            lecture_text = ""
        if driver.current_url != assignment.test_url:
            driver.get(assignment.test_url)

    if not lecture_text and is_final_test(assignment.test_name, assignment.topic_name):
        print(f"{prefix} 📚 Загружаем сохранённые лекции всего курса...")
        lecture_text = load_saved_course_context(assignment.course_name)

    if lecture_text:
        print(f"{prefix} 🧠 Контекст лекции: {len(lecture_text)} символов.")
    else:
        print(f"{prefix} 🤷 Лекция отсутствует; используем общие знания.")

    current_attempt = has_current_attempt(driver)
    if not lecture_text and REQUIRE_LECTURE_CONTEXT and not current_attempt:
        return QuizResult(error="Не удалось подготовить контекст лекции"), lecture_text

    is_last_retry = (
        requirements.allowed_attempts is not None
        and requirements.attempt_number is not None
        and requirements.attempt_number > 1
        and requirements.attempt_number >= requirements.allowed_attempts
        and not current_attempt
    )
    if is_last_retry and not AUTO_USE_LAST_ATTEMPT:
        return (
            QuizResult(error="Последняя повторная попытка оставлена для ручного запуска"),
            lecture_text,
        )

    if not start_test_attempt(driver):
        return QuizResult(error="Не удалось войти в назначенный тест"), lecture_text

    attempt_started_at = datetime.now().isoformat(timespec="seconds")
    attempt_start = time.time()
    result = solve_active_test(
        driver,
        lecture_text,
        course_name=assignment.course_name,
        test_name=assignment.test_name,
        requirements=requirements,
    )
    duration = time.time() - attempt_start
    record_attempt(
        run_id,
        assignment.course_name,
        assignment.test_name,
        result,
        duration_sec=duration,
        started_at=attempt_started_at,
    )

    if result.passed:
        print(f"{prefix} ✅ Тест пройден.")
    elif result.submitted:
        grade = (
            "неизвестно"
            if result.grade_percent is None
            else f"{result.grade_percent:.2f}%"
        )
        print(f"{prefix} 📉 Тест не пройден. Оценка: {grade}")

    return result, lecture_text


def _can_retry_result(result):
    if not result.submitted or result.passed or result.error:
        return False
    if result.remaining_attempts == 0:
        return False
    if result.remaining_attempts == 1 and not AUTO_USE_LAST_ATTEMPT:
        print("🛑 Последнюю попытку автоматически не используем.")
        return False
    return True


def _find_next_course_assignment(driver, previous, ignored_tests):
    driver.get(previous.course_url)
    test_name, test_url, topic_name = find_current_test_info(
        driver,
        ignore_test_urls=ignored_tests,
    )
    if not test_name or not test_url:
        print(f"✅ В курсе '{previous.course_name}' больше нет доступных тестов.")
        return None
    return CourseAssignment(
        course_url=previous.course_url,
        course_name=previous.course_name,
        test_name=test_name,
        test_url=test_url,
        topic_name=topic_name,
    )


def _create_driver():
    """Use the cached driver immediately and go online only when it cannot start."""
    os.environ["SE_AVOID_STATS"] = "true"
    os.environ["SE_OFFLINE"] = "true"

    try:
        print("🌐 Запуск Chrome с кешированным ChromeDriver...")
        return webdriver.Chrome(options=options)
    except WebDriverException as cached_error:
        print(f"⚠️ Кешированный ChromeDriver не подошёл: {cached_error.msg}")
        print("🌐 Пробуем найти или обновить ChromeDriver через интернет...")
        os.environ["SE_OFFLINE"] = "false"
        os.environ["SE_TIMEOUT"] = "15"
        return webdriver.Chrome(options=options)


def _load_lecture_text(driver, course_name, test_name, topic_name):
    if not topic_name:
        return ""

    print(f"📌 Тема из теста: '{topic_name}'\n")
    lecture_urls = find_lecture_urls(driver, topic_name, test_name=test_name)
    if not lecture_urls:
        return ""

    parts = []
    for index, lecture_url in enumerate(lecture_urls, start=1):
        prefix = topic_name if len(lecture_urls) == 1 else f"{topic_name}_часть_{index}"
        source_path = save_page_html(driver, lecture_url, prefix, course_name)
        if not source_path:
            continue

        lecture_text = clean_html_to_text(source_path)
        if is_context_error_text(lecture_text):
            print(f"⚠️ Не удалось извлечь часть лекции: {lecture_text}")
            continue

        save_text_file(lecture_text, source_path)
        parts.append(f"### Материал {index}\n{lecture_text}")

    if parts:
        print(f"📚 Объединено материалов по теме: {len(parts)}")
    return "\n\n".join(parts)


def _handle_failed_result(result, test_url, ignored_tests):
    if result.error:
        print(f"❌ Попытка не завершена: {result.error}")
        ignored_tests.add(test_url)
        return False

    grade = "неизвестно" if result.grade_percent is None else f"{result.grade_percent:.2f}%"
    print(f"📉 Тест не пройден. Оценка: {grade}")

    if result.remaining_attempts == 0:
        print("⛔ Попытки закончились; тест пропускается в этой сессии.")
        ignored_tests.add(test_url)
    elif result.remaining_attempts == 1 and not AUTO_USE_LAST_ATTEMPT:
        print("🛑 Последнюю попытку оставляем для ручного подтверждения.")
        ignored_tests.add(test_url)
        return True
    elif result.new_confirmed_answers <= 0:
        print("⏸️ Обзор не дал новых подтверждённых ответов; повторять ту же попытку сейчас не будем.")
        ignored_tests.add(test_url)
    else:
        print(
            f"🔁 Получено новых подтверждённых ответов: {result.new_confirmed_answers}. "
            "Тест можно перепройти."
        )

    return False


def _print_requirements(requirements):
    if requirements.pass_grade is not None:
        print(f"📏 Проходной балл: {requirements.pass_grade:.2f}%")
    if requirements.allowed_attempts is not None:
        print(
            f"🔢 Попытка: {requirements.attempt_number}/{requirements.allowed_attempts}; "
            f"после неё останется: {requirements.remaining_attempts_after_current}"
        )


def _print_start_stats(stats):
    print("\n🤖 MoodleBot v3.0. Запущено.")
    print(f"✅ Успешно пройдено: {stats['passed_tests']}")
    print(f"📝 Всего попыток: {stats['total_attempts']}")
    print(f"📉 Неудачных попыток: {stats['failed_attempts']}")
    print(f"⏹️ Прерванных попыток: {stats['interrupted_attempts']}")
    if stats["average_grade"] is not None:
        print(f"📊 Средняя оценка: {stats['average_grade']:.2f}%")
    print(f"⏳ Время в тестах: {format_duration(stats['total_test_time_sec'])}")
    print(f"⚡ Общее время работы: {format_duration(stats['total_uptime_sec'])}")
    if stats["total_questions"]:
        print(
            f"🧮 Ответы: {stats['correct_questions']} верных, "
            f"{stats['partial_questions']} частичных, "
            f"{stats['incorrect_questions']} неверных, "
            f"{stats['unanswered_questions']} без ответа, "
            f"{stats['ungraded_questions']} без оценки"
        )
    if stats["legacy_tests"]:
        print(
            f"ℹ️ Старые данные до перехода на БД: {stats['legacy_tests']} тестов, "
            f"{format_duration(stats['legacy_uptime_sec'])} работы"
        )
    print()


def _query_id(url):
    try:
        return (parse_qs(urlparse(url).query).get("id") or [""])[0]
    except Exception:
        return ""


if __name__ == "__main__":
    run()
