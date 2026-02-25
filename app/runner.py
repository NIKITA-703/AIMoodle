import time

from selenium import webdriver

from app.ai_utils import clean_html_to_text, save_text_file
from app.auth import login_on_mudl
from app.config import options, rand_user_agent, service, url_home_page, url_login
from app.flows.course_flow import find_current_test_info, get_current_course_link
from app.flows.lecture_flow import find_lecture_url, save_page_html, try_get_lecture_via_breadcrumbs
from app.stats import format_duration, get_global_stats, update_stats
from app.flows.test_flow import solve_active_test, start_test_attempt


def run():
    driver = None
    ignored_courses = set()  # <-- ЧЕРНЫЙ СПИСОК КУРСОВ

    # === СЧЕТЧИКИ ===
    TESTS_LIMIT = 13
    tests_completed = 0
    start_time_total = time.time()  # Засекаем время старта всего бота

    # Вывод статистики при старте
    stats = get_global_stats()
    print(f"\n🤖 MoodleBot v2.1. Запущено.")
    print(f"🏆 Всего пройдено: {stats['total_tests']}")
    print(f"⏳ Чистое время в тестах: {format_duration(stats['total_test_time_sec'])}")
    print(f"⚡ Общее время работы: {format_duration(stats['total_uptime_sec'])}\n")

    try:
        driver = webdriver.Chrome(service=service, options=options)

        driver.get(url_home_page)
        time.sleep(5)

        # Read cookies
        # try:
        #     with open("MAIN_COOKIES.pkl", "rb") as f:
        #         cookies = pickle.load(f)
        #     for cookie in cookies:
        #         driver.add_cookie(cookie)
        #     print("COOKIE was loaded \n")
        #
        #     time.sleep(25)
        #     driver.refresh()
        #     time.sleep(25)
        #     driver.get(url_home_page)
        # except FileNotFoundError:
        #     # Если файла нет, придётся логиниться "вручную"
        #     print("File MAIN_COOKIES is not found.First let's save new cookies after logins.\n")
        # except Exception as e:
        #     print(f"ERROR: {e} \n")
        # finally:
        #     pass

        driver.refresh()
        time.sleep(3)

        # if driver.current_url == url_login:
        if driver.current_url.startswith(url_login):
            login_on_mudl(driver)

            if driver.current_url.startswith(url_home_page):
                print(f"Авторизация прошла успешна! \n")
                print(f"URL NOW: {driver.current_url} \n")
                time.sleep(10)
                # COOKIES
                # with open("MAIN_COOKIES.pkl", "wb") as f:
                #     pickle.dump(driver.get_cookies(), f)
                # time.sleep(15)
                # driver.refresh()
                # print("New cookies were created \n")

                # Проверяем, вошли ли мы
            else:
                print("Не удалось попасть в ЛК.\n")
                print(f"URL NOW: {driver.current_url}\n")
                return

            # COOKIES
            # if driver.current_url != url_home_page:
            #     print("Something went wrong! \n")
            #     print(f"URL NOW: {driver.current_url}")
            # else:
            #     print(f"Authorization was successful! \n")
            #     print(f"URL NOW: {driver.current_url} \n")
            #     with open("MAIN_COOKIES", "wb") as f:
            #         pickle.dump(driver.get_cookies(), f)
            #     print("New cookies were created \n")
        else:
            print("Site was successfully opened:", driver.title, f"\n {driver.current_url} \n")
            driver.refresh()

        # driver.get(url_testes) -> преходит на тест в url_testes
        time.sleep(5)

        print("Используемый User-Agent:", rand_user_agent, "\n")

        # БЕСКОНЕЧНЫЙ ЦИКЛ ПО КУРСАМ
        while True:

            # 1. Проверка лимита
            if tests_completed >= TESTS_LIMIT:
                print(f"🎉 Лимит в {TESTS_LIMIT} тестов выполнен.\n")
                break

            print(f"\n🔎 Ищем активный курс (пропущено: {len(ignored_courses)})...\n")

            # Передаем черный список в поиск
            course_url, course_name = get_current_course_link(driver, ignore_urls=ignored_courses)

            if not course_url:
                print("🎉 Все доступные курсы обработаны! (Остались только с заданиями или завершенные).\n")
                break

            print(f"📘 Заходим в: {course_name}\n")
            driver.get(course_url)

            # Ищем тест
            test_name, test_url, topic_name = find_current_test_info(driver)

            if test_name and test_url:
                print(f"📝 Активный тест: {test_name}\n")

                lecture_text = ""
                # --- ЛОГИКА ЗАГРУЗКИ ЛЕКЦИИ ---
                # --- ПОПЫТКА 1: Поиск на главной странице ---
                if topic_name:
                    print(f"📌 Тема из теста: '{topic_name}'\n")
                    l_url = find_lecture_url(driver, topic_name, test_name=test_name)

                    if l_url:
                        h_path = save_page_html(driver, l_url, topic_name, course_name)
                        if h_path:
                            lecture_text = clean_html_to_text(h_path)
                            save_text_file(lecture_text, h_path)
                            print(f"🧠 Лекция загружена ({len(lecture_text)} симв).\n")
                        else:
                            print("❌ Ошибка: save_page_html вернула None.\n")
                    else:
                        print(f"⚠️ Ссылка на лекцию не найдена. ИИ будет решать без контекста.\n")
                else:
                    print(f"⚠️ Не удалось определить тему лекции (topic_name is None). ИИ будет решать без контекста.\n")
                # ------------------------------

                print("▶️ Старт теста...")
                driver.get(test_url)

                # --- ПОПЫТКА 2 (ПЛАН Б): Хлебные крошки ---
                # Если лекции нет, пробуем найти её через навигацию теста
                if not lecture_text:
                    print("⚠️ Лекция не найдена на главной. Пробуем через навигацию теста...")
                    lecture_text = try_get_lecture_via_breadcrumbs(driver, course_name)

                    # Если План Б сработал (мы уходили со страницы), нужно вернуться в тест
                    if driver.current_url != test_url:
                        print("🔙 Возвращаемся в тест...")
                        driver.get(test_url)

                if not lecture_text:
                    print("🤷‍♂️ Лекция так и не найдена. ИИ будет решать на общих знаниях.")

                # --- РЕШЕНИЕ ---
                if start_test_attempt(driver):
                    # === ЗАСЕКАЕМ ВРЕМЯ ТЕСТА ===
                    test_start_time = time.time()

                    solve_active_test(driver, lecture_text)

                    test_end_time = time.time()
                    duration = test_end_time - test_start_time

                    # Обновляем статистику (1 тест + время)
                    new_stats = update_stats(tests_added=1, test_time_added=duration)
                    tests_completed += 1
                    print(f"📊 Пройдено тестов: {tests_completed}/{TESTS_LIMIT}")

                # После теста возвращаемся на главную
                print("🔙 На главную...")
                driver.get(url_home_page)
                time.sleep(2)
            else:
                # !!! САМОЕ ВАЖНОЕ !!!
                print(f"⚠️ В курсе '{course_name}' нет активных тестов (возможно только Задания).")
                print(f"⛔ Добавляем курс в черный список на эту сессию.")
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

            # Красивый перевод в часы:минуты:секунды
            m, s = divmod(duration, 60)
            h, m = divmod(m, 60)

            print(f"\n⏱️ ОБЩЕЕ ВРЕМЯ РАБОТЫ: {int(h)}ч {int(m)}мин {int(s)}сек\n")

            driver.quit()
            print("Browser CLOSED")


if __name__ == "__main__":
    main()

if __name__ == "__main__":
    run()
