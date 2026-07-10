import time

from selenium import webdriver

from app.ai_utils import check_ai_ready, clean_html_to_text, is_context_error_text, save_text_file
from app.auth import login_on_mudl
from app.config import options, rand_user_agent, service, url_home_page, url_login
from app.flows.course_flow import find_current_test_info, get_current_course_link
from app.flows.lecture_flow import (
    find_lecture_url,
    is_final_test,
    load_saved_course_context,
    save_page_html,
    try_get_lecture_via_breadcrumbs,
)
from app.flows.test_flow import solve_active_test, start_test_attempt
from app.stats import format_duration, get_global_stats, update_stats


def run():
    driver = None
    ignored_courses = set()

    TESTS_LIMIT = 13
    tests_completed = 0
    start_time_total = time.time()

    stats = get_global_stats()
    print(f"\n🤖 MoodleBot v2.1. Запущено.")
    print(f"🏆 Всего пройдено: {stats['total_tests']}")
    print(f"⏳ Чистое время в тестах: {format_duration(stats['total_test_time_sec'])}")
    print(f"⚡ Общее время работы: {format_duration(stats['total_uptime_sec'])}\n")

    ai_ready, ai_message = check_ai_ready()
    if ai_ready:
        print(f"🧠 {ai_message}\n")
    else:
        print(f"❌ {ai_message}")
        print("⛔ Запуск бота остановлен. Сначала включи LM Studio и загрузи модель.\n")
        return

    try:
        driver = webdriver.Chrome(service=service, options=options)

        driver.get(url_home_page)
        time.sleep(5)

        driver.refresh()
        time.sleep(3)

        if driver.current_url.startswith(url_login):
            login_on_mudl(driver)

            if driver.current_url.startswith(url_home_page):
                print("Авторизация прошла успешна! \n")
                print(f"URL NOW: {driver.current_url} \n")
                time.sleep(10)
            else:
                print("Не удалось попасть в ЛК.\n")
                print(f"URL NOW: {driver.current_url}\n")
                return
        else:
            print("Site was successfully opened:", driver.title, f"\n {driver.current_url} \n")
            driver.refresh()

        time.sleep(5)

        print("Используемый User-Agent:", rand_user_agent, "\n")

        while True:
            if tests_completed >= TESTS_LIMIT:
                print(f"🎉 Лимит в {TESTS_LIMIT} тестов выполнен.\n")
                break

            print(f"\n🔎 Ищем активный курс (пропущено: {len(ignored_courses)})...\n")

            course_url, course_name = get_current_course_link(driver, ignore_urls=ignored_courses)

            if not course_url:
                print("🎉 Все доступные курсы обработаны! (Остались только с заданиями или завершенные).\n")
                break

            print(f"📘 Заходим в: {course_name}\n")
            driver.get(course_url)

            test_name, test_url, topic_name = find_current_test_info(driver)

            if test_name and test_url:
                print(f"📝 Активный тест: {test_name}\n")

                lecture_text = ""
                if topic_name:
                    print(f"📌 Тема из теста: '{topic_name}'\n")
                    l_url = find_lecture_url(driver, topic_name, test_name=test_name)

                    if l_url:
                        h_path = save_page_html(driver, l_url, topic_name, course_name)
                        if h_path:
                            lecture_text = clean_html_to_text(h_path)
                            if is_context_error_text(lecture_text):
                                print(f"⚠️ Не удалось извлечь текст лекции: {lecture_text}")
                                lecture_text = ""
                            else:
                                save_text_file(lecture_text, h_path)
                                print(f"🧠 Лекция загружена ({len(lecture_text)} симв).\n")
                        else:
                            print("❌ Ошибка: save_page_html вернула None.\n")
                    else:
                        print("⚠️ Ссылка на лекцию не найдена. ИИ будет решать без контекста.\n")
                else:
                    print("⚠️ Не удалось определить тему лекции (topic_name is None). ИИ будет решать без контекста.\n")

                print("▶️ Старт теста...")
                driver.get(test_url)

                if not lecture_text:
                    print("⚠️ Лекция не найдена на главной. Пробуем через навигацию теста...")
                    lecture_text = try_get_lecture_via_breadcrumbs(driver, course_name)

                    if is_context_error_text(lecture_text):
                        print(f"⚠️ План Б не смог извлечь текст лекции: {lecture_text}")
                        lecture_text = ""

                    if driver.current_url != test_url:
                        print("🔙 Возвращаемся в тест...")
                        driver.get(test_url)

                if not lecture_text:
                    print("🤷‍♂️ Лекция так и не найдена. ИИ будет решать на общих знаниях.")

                if not lecture_text and is_final_test(test_name, topic_name):
                    print("📚 Это итоговый тест. Пробуем собрать общий контекст по всему курсу из сохраненных лекций...")
                    lecture_text = load_saved_course_context(course_name)

                    if not lecture_text:
                        print("⚠️ Общий контекст курса для итогового теста пока не найден.")

                if start_test_attempt(driver):
                    test_start_time = time.time()
                    solve_active_test(driver, lecture_text, course_name=course_name, test_name=test_name)
                    test_end_time = time.time()
                    duration = test_end_time - test_start_time

                    update_stats(tests_added=1, test_time_added=duration)
                    tests_completed += 1
                    print(f"📊 Пройдено тестов: {tests_completed}/{TESTS_LIMIT}")

                print("🔙 На главную...")
                driver.get(url_home_page)
                time.sleep(2)
            else:
                print(f"⚠️ В курсе '{course_name}' нет активных тестов (возможно только Задания).")
                print("⛔ Добавляем курс в черный список на эту сессию.")
                ignored_courses.add(course_url)

                driver.get(url_home_page)
                time.sleep(2)

    except Exception as e:
        print(f"\n💀 GLOBAL ERROR: {e}")
    finally:
        if driver:
            end_time_total = time.time()
            duration = end_time_total - start_time_total

            update_stats(uptime_added=duration)

            m, s = divmod(duration, 60)
            h, m = divmod(m, 60)

            print(f"\n⏱️ ОБЩЕЕ ВРЕМЯ РАБОТЫ: {int(h)}ч {int(m)}мин {int(s)}сек\n")

            try:
                driver.quit()
                print("Browser CLOSED")
            except BaseException as e:
                print(f"⚠️ Не удалось корректно закрыть браузер: {e}")


if __name__ == "__main__":
    run()
