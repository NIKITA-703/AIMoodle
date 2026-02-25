import os
import re
import time
from datetime import datetime

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app.ai_utils import clean_html_to_text, save_text_file
from app.browser_utils import sanitize_filename


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

