import re
import time
import traceback
from datetime import datetime

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from app.ai_utils import ask_ai_question_data, normalize_text_answer
from app.config import BOT_HISTORY_FILE
from app.models import QuizRequirements, QuizResult
from app.quiz_memory import extract_question_id, get_confirmed_answer, record_review_results
from app.quiz_review import parse_quiz_requirements, parse_review_summary


class AIServiceError(RuntimeError):
    pass


class AnswerResolutionError(RuntimeError):
    pass


def get_quiz_requirements(driver, course_id="", quiz_id=""):
    return parse_quiz_requirements(driver.page_source, course_id=course_id, quiz_id=quiz_id)


def start_test_attempt(driver):
    print("🎯 Попытка начать тест... \n")
    try:
        if driver.find_elements(By.CSS_SELECTOR, ".que"):
            print("↩️ Попытка уже открыта, продолжаем текущий тест.\n")
            return True

        btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//button[contains(., 'Продолжить текущую попытку') "
                    "or contains(., 'Продолжить последнюю попытку') "
                    "or contains(., 'Пройти тест') "
                    "or contains(., 'Начать тестирование') "
                    "or contains(., 'Продолжить')]",
                )
            )
        )
        btn.click()

        try:
            confirm = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//input[@value='Начать попытку'] "
                        "| //button[contains(., 'Начать попытку')] "
                        "| //input[@value='Начать новую попытку'] "
                        "| //button[contains(., 'Начать новую попытку')]",
                    )
                )
            )
            confirm.click()
        except Exception:
            pass

        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".que")))
        print("🚀 Тест запущен!\n")
        return True
    except Exception as e:
        print(f"❌ Не удалось войти в тест: {e}\n")
        return False


def solve_active_test(
    driver,
    lecture_text,
    course_name="",
    test_name="",
    requirements=None,
):
    requirements = requirements or QuizRequirements()
    result = QuizResult(
        pass_grade=requirements.pass_grade,
        attempt_number=requirements.attempt_number,
        remaining_attempts=requirements.remaining_attempts_after_current,
    )
    print("\n🤖 [AGENT] Режим решения активирован.")

    while True:
        try:
            time.sleep(2)

            if not driver.find_elements(By.CSS_SELECTOR, ".que") and driver.find_elements(
                By.CSS_SELECTOR, ".quizsummaryofattempt"
            ):
                print("🏁 Вопросы кончились.")
                return submit_test(
                    driver,
                    course_name=course_name,
                    test_name=test_name,
                    requirements=requirements,
                    source_counts=result.source_counts,
                )

            question_blocks = driver.find_elements(By.CSS_SELECTOR, ".que")
            if not question_blocks:
                result.error = "Не найдены блоки вопросов"
                return result

            for q_block in question_blocks:
                source = _answer_question_block(
                    driver,
                    q_block,
                    lecture_text,
                    course_name=course_name,
                    test_name=test_name,
                    requirements=requirements,
                )
                if source in result.source_counts:
                    result.source_counts[source] += 1

            next_buttons = driver.find_elements(By.NAME, "next")
            if next_buttons:
                next_buttons[0].click()
                continue

            end_attempt_buttons = driver.find_elements(
                By.XPATH,
                "//input[contains(@value, 'Закончить попытку')] | //button[contains(., 'Закончить попытку')] | "
                "//input[contains(@value, 'Завершить попытку')] | //button[contains(., 'Завершить попытку')]",
            )
            if end_attempt_buttons:
                end_attempt_buttons[0].click()
                time.sleep(2)
                continue

            finish_buttons = driver.find_elements(
                By.XPATH,
                "//button[contains(., 'Отправить всё')] | //input[@value='Отправить всё и завершить тест']",
            )
            if finish_buttons:
                return submit_test(
                    driver,
                    course_name=course_name,
                    test_name=test_name,
                    requirements=requirements,
                    source_counts=result.source_counts,
                )

            result.error = "Не найдена кнопка перехода или завершения теста"
            return result
        except (AIServiceError, AnswerResolutionError) as e:
            result.error = str(e)
            print(f"🛑 Решение остановлено без отправки теста: {e}")
            return result
        except Exception as e:
            result.error = str(e)
            print(f"❌ Глобальная ошибка цикла: {e}")
            print(traceback.format_exc())
            return result


def submit_test(driver, course_name="", test_name="", requirements=None, source_counts=None):
    requirements = requirements or QuizRequirements()
    result = QuizResult(
        pass_grade=requirements.pass_grade,
        attempt_number=requirements.attempt_number,
        remaining_attempts=requirements.remaining_attempts_after_current,
        source_counts=dict(source_counts or {}),
    )

    try:
        finish_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(., 'Отправить всё')] | //input[@value='Отправить всё и завершить тест']")
            )
        )
        finish_btn.click()

        modal_confirm = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-action='save']"))
        )
        modal_confirm.click()

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".quizreviewsummary"))
        )
        print("✅ ТЕСТ ОТПРАВЛЕН!")

        summary = parse_results(driver)
        memory_result = record_review_results(
            driver,
            course_name,
            test_name,
            course_id=requirements.course_id,
            quiz_id=requirements.quiz_id,
        )

        result.submitted = True
        result.score = summary.score
        result.max_score = summary.max_score
        result.grade_percent = summary.grade_percent
        result.new_confirmed_answers = memory_result["new_confirmed_count"]

        if result.pass_grade is None:
            result.passed = True
        elif result.grade_percent is not None:
            result.passed = result.grade_percent + 1e-9 >= result.pass_grade

        status = "ПРОЙДЕН" if result.passed else "НЕ ПРОЙДЕН"
        print(f"📌 Результат: {status}")
        if result.pass_grade is not None:
            print(f"📏 Проходной балл: {result.pass_grade:.2f}%")
        return result
    except Exception as e:
        result.error = f"Ошибка финализации: {e}"
        print(f"⚠️ {result.error}\n")
        return result


def parse_results(driver):
    print("\n📊 --- ИТОГИ ТЕСТА ---")
    summary = parse_review_summary(driver.page_source)

    print(f"⏱️ Время: {summary.time_taken}")
    if summary.score is not None and summary.max_score is not None:
        print(f"🎯 Баллы: {summary.score:.2f}/{summary.max_score:.2f}")
    else:
        print("🎯 Баллы: не найдены")
    if summary.grade_percent is not None:
        print(f"🏆 Оценка: {summary.grade_percent:.2f}%")
    else:
        print("🏆 Оценка: не найдена")

    with open(BOT_HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(
            f"[{datetime.now()}] Время: {summary.time_taken} | "
            f"Баллы: {summary.score}/{summary.max_score} | "
            f"Оценка: {summary.grade_percent}%\n"
        )
    return summary


def extract_answers(ai_text):
    if ai_text is None:
        return []
    found = re.findall(r"\b([a-z0-9]+)[\.)]", str(ai_text).lower())
    if not found and len(str(ai_text).strip()) < 5:
        clean = str(ai_text).strip().lower().replace(".", "").replace(")", "")
        if clean:
            found = [clean]
    return found

def _answer_question_block(
    driver,
    q_block,
    lecture_text,
    course_name="",
    test_name="",
    requirements=None,
):
    requirements = requirements or QuizRequirements()
    q_text = q_block.find_element(By.CSS_SELECTOR, ".qtext").text.strip()
    question_label = "?"
    try:
        question_label = q_block.find_element(By.CSS_SELECTOR, ".qno").text.strip()
    except Exception:
        pass

    question_type, options_text, options_map, option_text_by_key, select_obj = _get_question_data(q_block)
    if _is_question_already_answered(q_block, question_type, options_map, select_obj):
        print(f"⏭️ Вопрос {question_label} уже заполнен, пропускаем.")
        return "existing"

    print(f"\n❓ Вопрос {question_label} ({question_type}): {q_text[:80]}...")
    question_id = extract_question_id(q_block)
    saved_answer = get_confirmed_answer(
        course_name,
        test_name,
        q_text,
        course_id=requirements.course_id,
        quiz_id=requirements.quiz_id,
        question_id=question_id,
    )

    target_keys = []
    text_answer = ""
    source = "memory" if saved_answer else "general_knowledge"

    if saved_answer:
        print(f"🧠 Используем подтверждённый ответ из памяти по qid={question_id or 'fallback'}.")
        if question_type == "text":
            text_answer = (saved_answer.get("text") or "").strip()
        elif question_type == "select":
            texts = saved_answer.get("texts") or []
            target_keys = texts[:1]
        else:
            target_keys = [key for key in saved_answer.get("keys", []) if key in options_map]
            if not target_keys:
                target_keys = _find_keys_by_texts(saved_answer.get("texts") or [], option_text_by_key)
    else:
        answer_hint = _get_text_answer_hint(q_text) if question_type == "text" else ""
        variants_str = "\n".join(options_text)
        ai_result = ask_ai_question_data(
            q_text,
            variants_str,
            lecture_text,
            question_type=question_type,
            answer_hint=answer_hint,
        )
        if ai_result.error:
            raise AIServiceError(ai_result.error)

        source = ai_result.source
        if ai_result.evidence:
            print(f"📖 Основание: {ai_result.evidence[:180]}")
        print(f"🧭 Источник ответа: {source}, контекст: {ai_result.context_mode}")

        if question_type == "text":
            text_answer = ai_result.text_answer or ai_result.raw_text
            text_answer = normalize_text_answer(q_text, text_answer, answer_hint=answer_hint)
        else:
            target_keys = [key for key in ai_result.answer_keys if key in options_map]
            if not target_keys:
                target_keys = [key for key in extract_answers(ai_result.raw_text) if key in options_map]
            if not target_keys:
                target_keys = _find_keys_by_texts([ai_result.raw_text], option_text_by_key)

    if question_type == "text":
        text_answer = _clean_text_answer(text_answer)
        if not text_answer:
            raise AnswerResolutionError(f"Вопрос {question_label}: ИИ не дал текстовый ответ")
        _fill_text_answer(driver, options_map, text_answer)
        print(f"🤖 Ответ: '{text_answer}'")
        return source

    if question_type == "select":
        if not target_keys:
            raise AnswerResolutionError(f"Вопрос {question_label}: не удалось определить вариант select")
        select_obj.select_by_visible_text(target_keys[0])
        print(f"🤖 Выбран вариант: {target_keys[0]}")
        return source

    if question_type == "radio" and len(target_keys) > 1:
        target_keys = target_keys[:1]
    target_keys = list(dict.fromkeys(target_keys))
    if not target_keys:
        raise AnswerResolutionError(f"Вопрос {question_label}: не удалось определить вариант ответа")

    for key in target_keys:
        element = options_map.get(key)
        if element is None:
            continue
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        if not element.is_selected():
            driver.execute_script("arguments[0].click();", element)
            time.sleep(0.2)

    print(f"🤖 Выбрано: {target_keys}")
    return source


def _get_question_data(q_block):
    options_text = []
    options_map = {}
    option_text_by_key = {}
    question_type = "unknown"
    select_obj = None

    select_elements = q_block.find_elements(By.TAG_NAME, "select")
    text_inputs = q_block.find_elements(By.CSS_SELECTOR, "input[type='text'][name^='q']")

    if select_elements:
        question_type = "select"
        select_obj = Select(select_elements[0])
        for option in select_obj.options:
            text = option.text.strip()
            if text and "выбрать" not in text.lower():
                options_text.append(text)
                options_map[text.lower()] = text
                option_text_by_key[text.lower()] = text
    elif text_inputs:
        question_type = "text"
        options_map["text_input"] = text_inputs[0]
    else:
        option_elements = q_block.find_elements(By.CSS_SELECTOR, ".answer div[class^='r']")
        for index, option in enumerate(option_elements):
            try:
                text = option.text.strip()
                try:
                    key = option.find_element(By.CSS_SELECTOR, ".answernumber").text.lower().strip(" .)")
                except Exception:
                    key = f"opt_{index}"
                input_el = option.find_element(By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox']")
                options_text.append(text)
                options_map[key] = input_el
                option_text_by_key[key] = text
                question_type = input_el.get_attribute("type") or question_type
            except Exception:
                continue

    return question_type, options_text, options_map, option_text_by_key, select_obj


def _is_question_already_answered(q_block, question_type, options_map, select_obj):
    try:
        state_text = q_block.find_element(By.CSS_SELECTOR, ".state").text.strip().lower()
        if "ответ сохранен" in state_text or "выполнен" in state_text:
            return True
    except Exception:
        pass

    if question_type == "text":
        input_el = options_map.get("text_input")
        return bool(input_el and (input_el.get_attribute("value") or "").strip())
    if question_type == "select" and select_obj:
        try:
            selected = select_obj.first_selected_option.text.strip()
            return bool(selected and "выбрать" not in selected.lower())
        except Exception:
            return False
    if question_type in {"radio", "checkbox"}:
        return any(_safe_selected(element) for element in options_map.values())
    return False


def _safe_selected(element):
    try:
        return element.is_selected()
    except Exception:
        return False


def _fill_text_answer(driver, options_map, text_answer):
    input_el = options_map.get("text_input")
    if input_el is None:
        raise AnswerResolutionError("Не найдено поле ввода текста")
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", input_el)
    input_el.clear()
    input_el.send_keys(text_answer)
    time.sleep(0.3)


def _clean_text_answer(answer):
    answer = re.sub(r"^\s*[a-zа-я0-9]+\s*[\.)]\s+", "", answer or "", flags=re.IGNORECASE)
    answer = re.sub(r"\s*\([^)]*\)", "", answer)
    return " ".join(answer.strip().strip('"').strip("'").strip(".").split())


def _get_text_answer_hint(question):
    gaps = re.findall(r"(?:\.{3,}|…)", question)
    if len(gaps) >= 2:
        return f"В вопросе {len(gaps)} пропуска; верни только необходимые слова в нужной форме."
    if len(gaps) == 1 or "вставьте недостающее слово" in question.lower():
        return "В вопросе один пропуск; верни только одно слово или короткий фрагмент в нужной форме."
    return ""


def _normalize_option_text(text):
    normalized = (text or "").strip().lower()
    normalized = re.sub(r"^\s*[a-zа-я0-9]+\s*[\.)]\s*", "", normalized, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", normalized).strip()


def _find_keys_by_texts(target_texts, option_text_by_key):
    found = []
    for target_text in target_texts:
        target = _normalize_option_text(target_text)
        if not target:
            continue
        for key, option_text in option_text_by_key.items():
            option = _normalize_option_text(option_text)
            if target == option or target in option or option in target:
                if key not in found:
                    found.append(key)
                break
    return found
