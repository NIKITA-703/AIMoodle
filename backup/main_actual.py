from datetime import datetime
import random
import time
import json
import os
import re

from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium import webdriver
from datetime import datetime

# Импорт твоих данных для входа (убедись, что файл auth_data.py существует)
from auth_data import login, password

# Импорт наших AI функций
from ai_utils import clean_html_to_text, save_text_file, ask_ai_question

# todo: cookies ❌(мб проверку кук убрать)⏳
# todo: продолжить делать. Начать делать чтение тестов, лекции к тесту и отправлять ИИ.
#  Проверить работу ИИ над лёгкими задачами ✅

# todo: Открывать и сохранять актуальный в html актуальный тест что ИИ могла взять контекст ✅

# todo: 1 Поиск актуального курса
# todo: 2 Поиск актуального теста
# todo: 2.1 Возможный заход на лекцию
# todo: 3. Сбор все задачи теста (уже проходя его) в файл
# todo: 4. Отправка тестов ИИ на принятие решения
# todo: 4.1 Если у ИИ появляются сомнения она должна прочитать лекцию
# todo: 5. Прокликивание радио баттона правильных ответов после принятия решения
# todo: 6. Отправка и подтверждение отправки теста
# todo: 7. Получить текущий результат (оценка за тест) записать куда-то
# todo: 8. Выйти на страницу курса и искать следующий тест для решения задач


# todo: СОБИРАТЬ ВОПРОСЫ С ТЕСТА ПЕРКЛЮЧАТСЯ МЕЖДУ НИМИ И ОТВЕЧАТЬ.
#  СНАЧАЛА СОБРАТЬ ВСЕ ВОПРОСЫ ПОЛУЧИТЬ ОТВЕТЫ ОТ ИИ И ОТВЕТИТЬ НА ВОПРОСЫ


# todo: ОТКРЫТЬ ТЕСТ СОБРАТЬ ВСЕ html и всё⏳⏳⏳⏳


# todo: переписать функции✅

# todo: ВЫТЯГИВАТЬ ТЕКСТ С ЛЕКЦИ !!!!✅

"""
    Отслеживать по <li id="section-XXX" ....>
    И проверить наличие
    <img src="https://lms.mitu.msk.ru/theme/image.php/mitu/quiz/1749497735/monologo?filtericon=1" ...> картинка таймера
    Перебирать сравнение id="section-XXX", если id="section-XXX" не будет совпадение между с друг другом (img src)
    Линейный поиск
"""

# ============ Webdriver Options ============

# options = Options()
options = webdriver.ChromeOptions()
# options.add_argument("--headless") # Включи потом, чтобы скрыть браузер
options.add_argument("-window-size=1590,950")  # --start-maximized

# Если Chromium лежит не в стандартном месте, через binary_location.
options.binary_location = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# ============ USER AGENT ============

# rand_user_agent = random.choice(list(open('user_agent.txt')))
# options.add_argument(f"user-agent={rand_user_agent}")

try:
    with open('user_agent.txt', 'r', encoding='utf-8') as f:
        user_agents = [line.strip() for line in f if line.strip()]
    rand_user_agent = random.choice(user_agents)
    options.add_argument(f"user-agent={rand_user_agent}")
except:
    pass

COOKIES_FILE = "moodle_cookies.pkl"

# ============ Chromium ============

driver_path = r'chromedriver.exe'
service = Service(driver_path)

# ============ URLS ============


url_home_page = "https://lms.mitu.msk.ru/my/"
url_login = "https://lms.mitu.msk.ru/login/index.php"

# DOMAIN_URL = "<https://lms.mitu.msk.ru>" # Основной домен
# url_now = driver.current_url  # Получает последнию страницу, а не каждый раз актуальную
# url_testes = "https://lms.mitu.msk.ru/course/view.php?id=89"


# ============ Function ============

STATS_FILE = "global_stats.json"


def format_duration(seconds):
    """Переводит секунды в формат 1ч 20м 5с"""
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}ч {m}м {s}с"


def get_global_stats():
    """Загружает статистику. Если полей нет (старый файл), добавляет нули."""
    default_stats = {
        "total_tests": 0,
        "total_test_time_sec": 0,  # Чистое время решения тестов
        "total_uptime_sec": 0,  # Общее время работы бота
        "last_run": ""
    }

    if not os.path.exists(STATS_FILE):
        return default_stats

    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Объединяем с дефолтными, чтобы не сломалось, если файл старый
            return {**default_stats, **data}
    except Exception:
        return default_stats


def update_stats(tests_added=0, test_time_added=0, uptime_added=0):
    """
    Универсальная функция обновления статистики.
    tests_added: сколько тестов прошли (0 или 1)
    test_time_added: сколько секунд ушло на решение
    uptime_added: сколько секунд работал бот (в конце сессии)
    """
    stats = get_global_stats()

    stats["total_tests"] += tests_added
    stats["total_test_time_sec"] += test_time_added
    stats["total_uptime_sec"] += uptime_added
    stats["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=4, ensure_ascii=False)

    return stats


def sanitize_filename(name):
    return "".join([c if c.isalnum() or c in " ._-" else "_" for c in name]).strip()
    """Удаляет запрещенные символы из имени файла/папки."""


def wait_for_element(driver: webdriver.Chrome, locator: tuple, timeout: float = 10) -> None:
    """Ожидает появления элемента на странице.
    Args:
        driver: Экземпляр веб-драйвера Selenium.
        locator: Кортеж, содержащий тип локатора (By.ID, By.XPATH и т.д.) и значение локатора.
        timeout: Максимальное время ожидания в секундах.
    Raises:
        TimeoutException: Если элемент не появился в течение указанного времени.
    """
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located(locator))
    except TimeoutException:
        print(f"Элемент не найден после {timeout} секунд.")
        raise
    # Пример использования:
    # wait_for_element(driver, (By.ID, "myDynamicElement")) #ожидание присутствия элемента
    # wait_for_element(driver, (By.XPATH, "//div[@class='loaded']")) #ожидание присутствия элемента
    # wait_for_element(driver, (By.CLASS_NAME, "some-class"), timeout=5) # Установка таймаута в 5 секунд


def login_on_mudl(driver):
    try:
        print(f"URL NOW: {driver.current_url}")
        # print(f"Logins....\n")

        print(f"🔐 Логинимся как {login}...")

        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, 'username')))

        """
            If username is the value of class attribute:
            login = driver.find_element(By.CLASS_NAME, "username")

            If username is the value of id attribute:
            login = driver.find_element(By.ID, "username")

            If username is the value of id attribute:
            login = driver.find_element(By.NAME, "username")

            If username is the value of linktext attribute:
            login = driver.find_element(By.LINK_TEXT, "username")
        """

        input_login = driver.find_element(By.ID, 'username')
        input_login.clear()
        input_login.send_keys(login)

        time.sleep(2)

        input_password = driver.find_element(By.ID, 'password')
        input_password.clear()
        input_password.send_keys(password)

        time.sleep(2)

        input_password.send_keys(Keys.ENTER)

        # time.sleep(7)
        # driver.get(url_home_page)

        # Ждём перехода на домашнюю страницу
        WebDriverWait(driver, 10).until(
            EC.url_contains("/my/")
        )
        print("✅ Успешный вход!")

    except Exception as e:
        print(f"❌ Ошибка входа: {e}")


def get_current_course_link(driver, ignore_urls=None):
    """
    Находит актуальный не пройденный курс.
    Возвращает (course_url, course_name).
    Находит курс со статусом 'Проходите сейчас'
    пропуская те, что в списке ignore_urls.
    """
    if ignore_urls is None:
        ignore_urls = set()

    try:
        # 1. Ждем появления хотя бы одного блока (для надежности)
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located(
                (By.XPATH,
                 "//div[contains(@class,'bcd-curriculum-discipline-state') and contains(text(),'Проходите сейчас')]")
            )
        )

        # 2. Находим ВСЕ элементы "Проходите сейчас" (а не только первый)
        all_states = driver.find_elements(By.XPATH,
                                          "//div[contains(@class,'bcd-curriculum-discipline-state') and contains(text(),'Проходите сейчас')]")

        print(f"🔎 Найдено активных курсов на странице: {len(all_states)}")

        for state_el in all_states:
            try:
                # Поднимаемся к ссылке
                link_el = state_el.find_element(By.XPATH, "./parent::div//a")
                url = link_el.get_attribute("href")
                name = link_el.text.strip()

                print(f"Имя курса: {name}")
                print(f"URL курса: {url}")

                # 3. Проверяем, не в черном ли списке этот курс
                if url not in ignore_urls:
                    return url, name

            except Exception as e:
                continue

        # Если прошли весь цикл и ничего не вернули — значит всё, что есть, уже проверено
        return None, None

    except Exception:
        return None, None


def find_current_test_info(driver, timeout=20):
    """
    Находит первый невыполненный тест.
    Возвращает кортеж: (test_name, test_url, topic_name)
    Находит активный тест
    """
    wait = WebDriverWait(driver, timeout)

    # --- Блок 1: Открываем вкладку "Элементы курса" и "Тесты" (как у тебя было) ---
    try:
        # Переход во вкладку 'Элементы курса'
        elem_course = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Элементы курса')]")))
        elem_course.click()

        # Разворачиваем блок с тестами
        tests_toggle = wait.until(EC.element_to_be_clickable((
            By.XPATH, "//h3[@id='quiz_overview_title']/preceding-sibling::a"
        )))
        # Проверяем атрибут aria-expanded, чтобы не кликать, если уже открыто
        if tests_toggle.get_attribute("aria-expanded") == "false":
            tests_toggle.click()

        # Ждем строки таблицы
        wait.until(
            EC.presence_of_element_located((By.XPATH, "//div[@id='quiz_overview']//tr[@data-mdl-overview-cmid]")))

    except Exception as e:
        print(f"❌ Ошибка навигации к тестам: {e}")
        return None, None, None

    # --- Блок 2: Поиск нужного теста ---
    rows = driver.find_elements(By.XPATH, "//div[@id='quiz_overview']//tr[@data-mdl-overview-cmid]")

    for row in rows:
        try:
            # Проверяем статус выполнения
            completion_td = row.find_element(By.XPATH, ".//td[@data-mdl-overview-item='completion']")
            value = completion_td.get_attribute("data-mdl-overview-value")  # "0" = надо сделать

            if value == "0":
                # 1. Имя теста и ссылка
                name_el = row.find_element(By.XPATH, ".//a[contains(@class,'activityname')]")
                test_name = name_el.text.strip()
                test_url = name_el.get_attribute("href")

                # 2. Имя темы (лекции). Оно лежит в div с классом small под именем теста
                # Смотрим HTML: <div class="small">Тема 4. Ядро операционной системы</div>
                try:
                    topic_el = row.find_element(By.XPATH, ".//div[contains(@class, 'small')]")
                    topic_name = topic_el.text.strip()
                except:
                    topic_name = None
                    print(f"⚠️ Тема для теста '{test_name}' не найдена.")

                print(f"✅ Найден тест: {test_name}")
                print(f"📌 Тема лекции: {topic_name} \n")
                return test_name, test_url, topic_name

        except Exception as e:
            continue

    print("Все активные тесты выполнены.")
    return None, None, None


def find_lecture_url(driver, target_topic_name, test_name=None, timeout=10):
    """
    Ищет лекцию в блоках 'Ресурсы' (resource) И 'Лекции' (lesson).
    Игнорирует различия 'Тема'/'Лекция'.
    """
    if not target_topic_name:
        return None

    wait = WebDriverWait(driver, timeout)
    print(f"🔎 Ищем материал для темы: '{target_topic_name}'...")

    # === ФУНКЦИЯ НОРМАЛИЗАЦИИ ===
    def normalize_name(text):
        # 1. В нижний регистр
        t = text.lower().strip()
        # 2. Вырезаем слова "тема", "лекция" и т.д. в начале
        t = re.sub(r'^(тема|лекция|глава|раздел|занятие|практика)\s*', '', t)
        # 3. Убираем лишние символы
        return t.strip(" .:-")

    def extract_number(text):
        # Ищет паттерны вида "2.3", "2.1", "5", "1.4.2"
        # \d+ - цифры, (?:[\.,]\d+)* - точка или запятая и цифры (опционально)
        match = re.search(r'\b(\d+(?:[\.,]\d+)*)\b', text)
        if match:
            return match.group(1).replace(',', '.')  # Унифицируем 2,3 -> 2.3
        return None

    # 1. Вычисляем номер теста (если он есть)
    target_number = None
    if test_name:
        target_number = extract_number(test_name)
        if target_number:
            print(f"   (debug) Ориентир по номеру: '{target_number}'")

    # 2. Вычисляем суть темы (для старого метода)
    target_clean = normalize_name(target_topic_name) if target_topic_name else None
    print(f"   (debug) Ищем суть: '{target_clean}'")

    # СПИСОК РАЗДЕЛОВ ДЛЯ ПОИСКА
    # resource = Обычные страницы/файлы
    # lesson = Модуль "Лекция" (как у тебя сейчас)
    section_types = ["resource", "lesson", "page"]

    for section in section_types:
        try:
            # Строим ID для конкретного раздела
            # Пример: id="resource_overview" или id="lesson_overview"
            overview_id = f"{section}_overview"
            title_id = f"{section}_overview_title"

            # Проверяем, есть ли вообще такой раздел на странице
            # (используем find_elements, чтобы не ждать timeout, если раздела нет)
            if not driver.find_elements(By.ID, overview_id) and not driver.find_elements(By.ID, title_id):
                continue

            # 1. Разворачиваем раздел (если свернут)
            try:
                toggle_xpath = f"//h3[@id='{title_id}']/preceding-sibling::a"
                res_toggle = driver.find_element(By.XPATH, toggle_xpath)

                # Moodle может прятать контент, кликаем если collapsed
                if res_toggle.get_attribute("aria-expanded") == "false":
                    driver.execute_script("arguments[0].click();", res_toggle)
                    time.sleep(1)
            except:
                pass  # Если переключателя нет или он не кликабелен, пробуем читать так

            # 2. Ищем строки таблицы внутри раздела
            rows_xpath = f"//div[@id='{overview_id}']//tr"
            rows = driver.find_elements(By.XPATH, rows_xpath)

            found_candidates = []

            for row in rows:
                try:
                    link_el = row.find_element(By.XPATH, ".//a[contains(@class,'activityname')]")
                    resource_name = link_el.text.strip()
                    url = link_el.get_attribute("href")

                    # Нормализуем имя найденного ресурса
                    resource_clean = normalize_name(resource_name)

                    # === ПРОВЕРКА 1: ПО НОМЕРУ (Самая надежная) ===
                    if target_number:
                        res_num = extract_number(resource_name)
                        if res_num == target_number:
                            print(f"✅ Найдено по номеру {target_number}: '{resource_name}'")
                            return url

                    # === ПРОВЕРКА 2: ПО ТЕМЕ (Запасная) ===
                    if target_clean == resource_clean or \
                            (len(target_clean) > 5 and target_clean in resource_clean) or \
                            (len(resource_clean) > 5 and resource_clean in target_clean):
                        print(f"✅ Найдено в разделе '{section}': '{resource_name}' -> {url}")
                        found_candidates.append(url)
                except:
                    continue

        except Exception as e:
            print(f"⚠️ Ошибка при проверке раздела {section}: {e}")
            continue

    # Если по номеру не нашли, но нашли по теме — возвращаем первый вариант по теме
    if found_candidates:
        print(f"✅ Найдено по названию темы (Plan B): {len(found_candidates)} шт.")
        return found_candidates[0]

    print("❌ Лекция не найдена ни в Ресурсах, ни в Лекциях.")
    return None


def save_page_html(driver, url, file_prefix="lecture", course_name="General_Course"):
    """
    Сохраняет HTML и ВОЗВРАЩАЕТ ПУТЬ к файлу
    """
    try:
        print(f"Переходим к лекции: {url} \n")
        driver.get(url)

        # Увеличиваем время ожидания загрузки страницы до 60 сек (из-за игр/торрентов)
        driver.set_page_load_timeout(60)

        try:
            driver.get(url)
        except TimeoutException:
            print("⚠️ Страница грузится слишком долго! Пробуем сохранить то, что есть...")
            driver.execute_script("window.stop();")  # Останавливаем загрузку (картинок и скриптов)

        # Ждем хотя бы body, если его нет - значит совсем беда
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        except:
            print("❌ Страница пустая или не загрузилась.")
            return None

        # 1. Подготовка имен
        safe_course = sanitize_filename(course_name)
        safe_prefix = sanitize_filename(file_prefix)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        # 2. Создаем путь: HTML Courses / Имя Курса
        base_folder = "HTML Courses"
        course_folder = os.path.join(base_folder, safe_course)

        if not os.path.exists(course_folder):
            os.makedirs(course_folder)
            print(f"📁 Создана папка курса: {course_folder}")

        # 3. Формируем полный путь к файлу
        filename = f"{safe_prefix}_{timestamp}.html"
        full_path = os.path.join(course_folder, filename)

        # 4. Сохраняем
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print(f"💾 Лекция сохранена: {full_path} \n")
        return full_path

    except Exception as e:
        print(f"❌ Не удалось сохранить лекцию: {e} \n")
        return None


def start_test_attempt(driver):
    """Нажимает 'Пройти тест' и подтверждает."""
    print("🎯 Попытка начать тест... \n")
    try:
        # 1. Кнопка "Пройти тест"
        # 1. Ищем кнопку запуска. Добавили 'Продолжить'
        btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH,
                                        "//button[contains(., 'Пройти тест') or contains(., 'Начать тестирование') or contains(., 'Продолжить')]"))
        )
        btn.click()

        # 2. Модалка "Начать попытку"
        try:
            confirm = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//input[@value='Начать попытку'] | //button[contains(., 'Начать попытку')]"))
            )
            confirm.click()
        except:
            pass  # Может и не быть

        # 3. Ждем появления вопроса
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".que")))
        print("🚀 Тест запущен!\n")
        return True
    except Exception as e:
        print(f"❌ Не удалось войти в тест: {e}\n")
        return False


def extract_answers(ai_text):
    """
    Умный парсинг ответа ИИ.
    Ищет буквы (a-z) или цифры (0-9) перед точкой или скобкой.
    """
    # 1. Ищем явные списки: "a.", "b)", "1.", "1)"
    # [a-z0-9] - любая буква или цифра
    found = re.findall(r'\b([a-z0-9]+)[\.\)]', ai_text.lower())

    # 2. Если не нашли, и ответ очень короткий (например просто "a" или "да"), берем весь текст
    if not found and len(ai_text) < 5:
        clean = ai_text.strip().lower().replace('.', '').replace(')', '')
        if clean:
            found = [clean]

    return found


def solve_active_test(driver, lecture_text):
    print("\n🤖 [AGENT] Режим решения активирован.")

    while True:
        try:
            time.sleep(1.5)

            # --- ПРОВЕРКА НА КОНЕЦ ---
            # Если нет вопросов, но есть саммари -> сдаем
            if not driver.find_elements(By.CSS_SELECTOR, ".que") and driver.find_elements(By.CSS_SELECTOR,
                                                                                          ".quizsummaryofattempt"):
                print("🏁 Вопросы кончились.")
                submit_test(driver)
                break

            # --- ПАРСИНГ ---
            q_block = driver.find_element(By.CSS_SELECTOR, ".que")
            try:
                q_text = q_block.find_element(By.CSS_SELECTOR, ".qtext").text.strip()
            except:
                q_text = "Текст вопроса не найден"

            # Собираем варианты
            options_elements = q_block.find_elements(By.CSS_SELECTOR, ".answer div[class^='r']")
            options_text = []
            options_map = {}
            question_type = "unknown"

            for index, opt in enumerate(options_elements):
                try:
                    # 1. Текст варианта
                    txt = opt.text.strip()
                    options_text.append(txt)

                    # 2. Ищем Ключ (Букву)
                    try:
                        key = opt.find_element(By.CSS_SELECTOR, ".answernumber").text.lower().strip(" .)")
                    except NoSuchElementException:
                        key = "opt_" + str(index)

                    # 3. Ищем Input (ВЫНЕСЕНО ИЗ БЛОКА EXCEPT!)
                    # Ищем строго radio или checkbox, игнорируя hidden
                    try:
                        inp = opt.find_element(By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox']")
                    except NoSuchElementException:
                        # Fallback
                        inp = opt.find_element(By.TAG_NAME, "input")

                    # 4. Записываем в словарь
                    options_map[key] = inp

                    # 5. Определяем тип (если еще не определили)
                    if question_type == "unknown":
                        question_type = inp.get_attribute("type")

                except Exception as e:
                    continue

            print(f"\n❓ Вопрос: {q_text[:80]}...")
            # print(f"   (Debug) Найдено вариантов: {len(options_map)}. Ключи: {list(options_map.keys())}")

            # --- ЦИКЛ ПОПЫТОК (RETRY) ---
            target_keys = []
            max_retries = 3

            for attempt in range(max_retries):
                variants_str = "\n".join(options_text)
                ai_ans = ask_ai_question(q_text, variants_str, lecture_text)

                extracted_all = extract_answers(ai_ans)

                # --- ЛОГИКА ВЫБОРА ---
                if question_type == 'radio':
                    # Для радио берем последнюю букву
                    if extracted_all:
                        valid_keys = [extracted_all[-1]]
                        # Проверяем наличие
                        if valid_keys[0] not in options_map:
                            # Если последней нет, ищем любую подходящую с конца
                            valid_keys = [k for k in reversed(extracted_all) if k in options_map][:1]
                    else:
                        valid_keys = []
                else:
                    # Для чекбоксов - все уникальные, которые есть на странице
                    valid_keys = list(set([k for k in extracted_all if k in options_map]))

                if valid_keys:
                    print(f"🤖 ИИ выбрал: {valid_keys}")
                    target_keys = valid_keys
                    break
                else:
                    print(f"⚠️ Попытка {attempt + 1}: ИИ дал '{extracted_all}', не подходит. Ждем...")
                    time.sleep(1)

            # --- FALLBACK (Если ИИ не справился) ---
            if not target_keys:
                print("🆘 ИИ не справился. Выбираем ПЕРВЫЙ вариант.")
                if options_map:
                    # Берем первый доступный ключ
                    first_key = list(options_map.keys())[0]
                    target_keys = [first_key]

            # --- КЛИК ---
            for key in target_keys:
                if key in options_map:
                    el = options_map[key]
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)

                    is_selected = el.is_selected()
                    if not is_selected:
                        driver.execute_script("arguments[0].click();", el)
                        time.sleep(0.3)

            # --- ДАЛЕЕ ---
            try:
                driver.find_element(By.NAME, "next").click()
            except:
                pass

        except Exception as e:
            print(f"❌ Ошибка цикла: {e}")
            break


def parse_results(driver):
    """
    Парсит итоговую таблицу Moodle после завершения теста.
    """
    print("\n📊 --- ИТОГИ ТЕСТА ---")
    try:
        # Ждем появления таблицы с результатами
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".quizreviewsummary"))
        )

        # 1. Время
        # Ищем h5 "Затраченное время" -> берем соседа div
        try:
            time_taken = driver.find_element(By.XPATH,
                                             "//h5[contains(., 'Затраченное время')]/following-sibling::div").text
            print(f"⏱️ Время: {time_taken}")
        except:
            time_taken = "Не найдено"

        # 2. Баллы
        try:
            points = driver.find_element(By.XPATH, "//h5[contains(., 'Баллы')]/following-sibling::div").text
            print(f"🎯 Баллы: {points}")
        except:
            points = "-"

        # 3. Оценка
        try:
            grade = driver.find_element(By.XPATH, "//h5[contains(., 'Оценка')]/following-sibling::div").text
            print(f"🏆 Оценка: {grade}")
        except:
            grade = "-"

        # Логируем в файл
        with open("bot_history.log", "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now()}] Время: {time_taken} | Баллы: {points} | Оценка: {grade}\n")

    except Exception as e:
        print(f"⚠️ Не удалось прочитать статистику: {e}")


def try_get_lecture_via_breadcrumbs(driver, course_name):
    """
    ПЛАН Б: Заходит в хлебные крошки теста, переходит в секцию темы
    и пытается найти там лекцию.
    """
    print("🕵️ ПЛАН Б: Пытаемся найти лекцию через навигацию (хлебные крошки)...")

    try:
        # 1. Ищем хлебные крошки
        # Обычно это список <ol class="breadcrumb"> -> <li> -> <a>
        breadcrumbs = driver.find_elements(By.CSS_SELECTOR, ".breadcrumb .breadcrumb-item a")

        if len(breadcrumbs) < 2:
            print("❌ Хлебные крошки слишком короткие.")
            return None

        # 2. Ищем ссылку на СЕКЦИЮ (section.php)
        # Это самая надежная ссылка на тему.
        target_link = None

        for link in reversed(breadcrumbs):
            href = link.get_attribute("href")

            # Если нашли ссылку на секцию - это то, что нужно
            if "course/section.php" in href:
                target_link = link
                break

        if not target_link:
            print("❌ Не нашли ссылку на секцию (section.php) в крошках.")
            return None

        topic_url = target_link.get_attribute("href")
        topic_name = target_link.text.strip()
        print(f"   -> Переходим в тему: {topic_name}")

        driver.get(topic_url)

        # 3. Мы внутри темы. Ищем материалы.
        # Ищем все ссылки на активности
        # Нам нужны: page, resource, lesson, url. Игнорируем: quiz, assign, forum.

        wait = WebDriverWait(driver, 5)
        activities = driver.find_elements(By.XPATH, "//div[contains(@class,'activity-instance')]//a")

        found_url = None
        found_name = ""

        for act in activities:
            href = act.get_attribute("href")
            name = act.text.strip()

            # Фильтр ненужного
            if any(x in href for x in ["mod/quiz", "mod/assign", "mod/forum", "mod/feedback"]):
                continue

            # Фильтр полезного
            if any(x in href for x in ["mod/page", "mod/resource", "mod/lesson", "mod/url"]):
                print(f"✅ Нашли материал в секции: {name}")
                found_url = href
                found_name = name
                # Если в названии есть слово "Лекция" - это приоритет, берем сразу
                if "лекция" in name.lower():
                    break
                # Иначе просто запоминаем первую найденную и ищем дальше (вдруг дальше будет именно Лекция)
                if not found_url:
                    found_url = href
                    found_name = name

        if found_url:
            # Сохраняем
            h_path = save_page_html(driver, found_url, f"Breadcrumb_{found_name}", course_name)
            if h_path:
                text = clean_html_to_text(h_path)
                save_text_file(text, h_path)
                return text

        print("❌ В этой секции нет текстовых материалов.")
        return None

    except Exception as e:
        print(f"❌ Ошибка Плана Б: {e}")
        return None


def submit_test(driver):
    """Отправляет тест на проверку"""
    try:
        # Ищем кнопку "Отправить всё и завершить тест"
        # Она может быть в разных местах, ищем по тексту
        finish_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(., 'Отправить всё')] | //input[@value='Отправить всё и завершить тест']"))
        )
        finish_btn.click()

        # Подтверждение в модалке
        modal_confirm = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-action='save']"))
        )
        modal_confirm.click()

        print("✅ ТЕСТ ЗАВЕРШЕН!")
        time.sleep(3)

        # ПАРСИМ РЕЗУЛЬТАТ
        parse_results(driver)
        time.sleep(2)

        # Возврат на главную
        driver.get(url_home_page)
        time.sleep(2)

    except Exception as e:
        print(f"⚠️ Ошибка финализации (возможно уже отправлен): {e}\n")
        driver.get(url_home_page)


def main():
    driver = None
    ignored_courses = set()  # <-- ЧЕРНЫЙ СПИСОК КУРСОВ

    # === СЧЕТЧИКИ ===
    TESTS_LIMIT = 30
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
                    print(
                        f"⚠️ Не удалось определить тему лекции (topic_name is None). ИИ будет решать без контекста.\n")
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