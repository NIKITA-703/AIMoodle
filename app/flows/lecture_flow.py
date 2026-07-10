import os
import re
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app.ai_utils import clean_html_to_text, save_text_file
from app.browser_utils import sanitize_filename


def find_lecture_url(driver, target_topic_name, test_name=None, timeout=10):
    """
    Ищет лекцию в блоках 'Ресурсы' (resource) и 'Лекции' (lesson).
    Игнорирует различия 'Тема'/'Лекция'.
    """
    if not target_topic_name:
        return None

    wait = WebDriverWait(driver, timeout)
    print(f"🔎 Ищем материал для темы: '{target_topic_name}'...")

    def normalize_name(text):
        t = text.lower().strip()
        t = re.sub(r"^(тема|лекция|глава|раздел|занятие|практика)\s*", "", t)
        return t.strip(" .:-")

    def extract_number(text):
        match = re.search(r"\b(\d+(?:[\.,]\d+)*)\b", text)
        if match:
            return match.group(1).replace(",", ".")
        return None

    target_number = None
    if test_name:
        target_number = extract_number(test_name)
        if target_number:
            print(f"   (debug) Ориентир по номеру: '{target_number}'")

    target_clean = normalize_name(target_topic_name) if target_topic_name else None
    print(f"   (debug) Ищем суть: '{target_clean}'")

    section_types = ["resource", "lesson", "page"]
    found_candidates = []

    for section in section_types:
        try:
            overview_id = f"{section}_overview"
            title_id = f"{section}_overview_title"

            if not driver.find_elements(By.ID, overview_id) and not driver.find_elements(By.ID, title_id):
                continue

            try:
                toggle_xpath = f"//h3[@id='{title_id}']/preceding-sibling::a"
                res_toggle = driver.find_element(By.XPATH, toggle_xpath)
                if res_toggle.get_attribute("aria-expanded") == "false":
                    driver.execute_script("arguments[0].click();", res_toggle)
                    time.sleep(1)
            except Exception:
                pass

            rows_xpath = f"//div[@id='{overview_id}']//tr"
            rows = driver.find_elements(By.XPATH, rows_xpath)

            for row in rows:
                try:
                    link_el = row.find_element(By.XPATH, ".//a[contains(@class,'activityname')]")
                    resource_name = link_el.text.strip()
                    url = link_el.get_attribute("href")
                    resource_clean = normalize_name(resource_name)

                    if target_number:
                        res_num = extract_number(resource_name)
                        if res_num == target_number:
                            print(f"✅ Найдено по номеру {target_number}: '{resource_name}'")
                            return url

                    if (
                        target_clean == resource_clean
                        or (len(target_clean) > 5 and target_clean in resource_clean)
                        or (len(resource_clean) > 5 and resource_clean in target_clean)
                    ):
                        print(f"✅ Найдено в разделе '{section}': '{resource_name}' -> {url}")
                        found_candidates.append(url)
                except Exception:
                    continue
        except Exception as e:
            print(f"⚠️ Ошибка при проверке раздела {section}: {e}")
            continue

    if found_candidates:
        print(f"✅ Найдено по названию темы (Plan B): {len(found_candidates)} шт.")
        return found_candidates[0]

    print("❌ Лекция не найдена ни в Ресурсах, ни в Лекциях.")
    return None


def _build_authenticated_session(driver):
    session = requests.Session()

    try:
        user_agent = driver.execute_script("return navigator.userAgent;")
        if user_agent:
            session.headers["User-Agent"] = user_agent
    except Exception:
        pass

    for cookie in driver.get_cookies():
        try:
            session.cookies.set(cookie["name"], cookie["value"])
        except Exception:
            continue

    return session


def _extract_embedded_file_url(page_url, html_text):
    soup = BeautifulSoup(html_text, "html.parser")

    for tag in soup.find_all(["iframe", "embed", "object"]):
        src = tag.get("src") or tag.get("data")
        if src:
            return urljoin(page_url, src)

    for tag in soup.find_all("a", href=True):
        href = urljoin(page_url, tag["href"])
        href_lower = href.lower()
        if ".pdf" in href_lower or "pluginfile.php" in href_lower or "forcedownload=1" in href_lower:
            return href

    return None


def _save_binary_file(content, full_path):
    with open(full_path, "wb") as f:
        f.write(content)


def save_page_html(driver, url, file_prefix="lecture", course_name="General_Course"):
    """
    Сохраняет HTML или PDF и возвращает путь к файлу.
    """
    try:
        safe_course = sanitize_filename(course_name)
        safe_prefix = sanitize_filename(file_prefix)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        base_folder = "HTML Courses"
        course_folder = os.path.join(base_folder, safe_course)

        if not os.path.exists(course_folder):
            os.makedirs(course_folder)
            print(f"📁 Создана папка курса: {course_folder}")

        print(f"Переходим к лекции: {url} \n")

        session = _build_authenticated_session(driver)

        try:
            response = session.get(url, timeout=60, allow_redirects=True)
            content_type = response.headers.get("Content-Type", "").lower()

            if response.ok and ("application/pdf" in content_type or response.content.startswith(b"%PDF")):
                full_path = os.path.join(course_folder, f"{safe_prefix}_{timestamp}.pdf")
                _save_binary_file(response.content, full_path)
                print(f"💾 PDF лекции сохранен: {full_path} \n")
                return full_path

            if response.ok and "text/html" in content_type:
                embedded_file_url = _extract_embedded_file_url(response.url, response.text)
                if embedded_file_url:
                    embedded_response = session.get(embedded_file_url, timeout=60, allow_redirects=True)
                    embedded_type = embedded_response.headers.get("Content-Type", "").lower()
                    if embedded_response.ok and (
                        "application/pdf" in embedded_type or embedded_response.content.startswith(b"%PDF")
                    ):
                        full_path = os.path.join(course_folder, f"{safe_prefix}_{timestamp}.pdf")
                        _save_binary_file(embedded_response.content, full_path)
                        print(f"💾 PDF лекции сохранен: {full_path} \n")
                        return full_path
        except Exception as e:
            print(f"⚠️ Не удалось скачать материал напрямую, пробуем через браузер: {e}")

        driver.get(url)
        driver.set_page_load_timeout(60)

        try:
            driver.get(url)
        except TimeoutException:
            print("⚠️ Страница грузится слишком долго! Пробуем сохранить то, что есть...")
            driver.execute_script("window.stop();")

        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        except Exception:
            print("❌ Страница пустая или не загрузилась.")
            return None

        full_path = os.path.join(course_folder, f"{safe_prefix}_{timestamp}.html")
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print(f"💾 Лекция сохранена: {full_path} \n")
        return full_path
    except Exception as e:
        print(f"❌ Не удалось сохранить лекцию: {e} \n")
        return None


def try_get_lecture_via_breadcrumbs(driver, course_name):
    """
    ПЛАН Б: заходит в хлебные крошки теста, переходит в секцию темы
    и пытается найти там лекцию.
    """
    print("🕵️ ПЛАН Б: Пытаемся найти лекцию через навигацию (хлебные крошки)...")

    try:
        breadcrumbs = driver.find_elements(By.CSS_SELECTOR, ".breadcrumb .breadcrumb-item a")

        if len(breadcrumbs) < 2:
            print("❌ Хлебные крошки слишком короткие.")
            return None

        target_link = None
        for link in reversed(breadcrumbs):
            href = link.get_attribute("href")
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

        activities = driver.find_elements(By.XPATH, "//div[contains(@class,'activity-instance')]//a")

        found_url = None
        found_name = ""

        for act in activities:
            href = act.get_attribute("href")
            name = act.text.strip()

            if any(x in href for x in ["mod/quiz", "mod/assign", "mod/forum", "mod/feedback"]):
                continue

            if any(x in href for x in ["mod/page", "mod/resource", "mod/lesson", "mod/url"]):
                print(f"✅ Нашли материал в секции: {name}")
                found_url = href
                found_name = name
                if "лекция" in name.lower():
                    break

        if found_url:
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


def is_final_test(test_name="", topic_name=""):
    haystack = f"{test_name} {topic_name}".lower()
    return "итогов" in haystack or "экзамен" in haystack or "зачет" in haystack



def load_saved_course_context(course_name, max_chars=18000):
    """
    Собирает единый контекст по курсу из уже сохраненных материалов.
    Сначала использует .txt, если их нет — пытается извлечь текст из .html/.pdf.
    """
    safe_course = sanitize_filename(course_name)
    course_folder = os.path.join("HTML Courses", safe_course)

    if not os.path.exists(course_folder):
        print(f"⚠️ Для курса '{course_name}' еще нет сохраненной папки с лекциями.")
        return ""

    txt_files = sorted(
        [os.path.join(course_folder, name) for name in os.listdir(course_folder) if name.lower().endswith(".txt")]
    )

    if not txt_files:
        source_files = sorted(
            [
                os.path.join(course_folder, name)
                for name in os.listdir(course_folder)
                if name.lower().endswith((".html", ".pdf"))
            ]
        )

        for source_path in source_files:
            text = clean_html_to_text(source_path)
            if text and not text.startswith("❌"):
                txt_path = save_text_file(text, source_path)
                if txt_path:
                    txt_files.append(txt_path)

    if not txt_files:
        print(f"⚠️ В папке курса '{course_name}' не найдено текстовых материалов для итогового контекста.")
        return ""

    parts = []
    total_len = 0

    for txt_path in txt_files:
        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                text = f.read().strip()
        except Exception:
            continue

        if not text or text.startswith("❌"):
            continue

        title = os.path.splitext(os.path.basename(txt_path))[0]
        chunk = f"\n\n### {title}\n{text}"

        if total_len + len(chunk) > max_chars:
            remaining = max_chars - total_len
            if remaining > 500:
                parts.append(chunk[:remaining])
            break

        parts.append(chunk)
        total_len += len(chunk)

    combined = "".join(parts).strip()

    if combined:
        print(f"📚 Собран общий контекст курса '{course_name}' ({len(combined)} симв).")
    else:
        print(f"⚠️ Не удалось собрать общий контекст курса '{course_name}'.")

    return combined
