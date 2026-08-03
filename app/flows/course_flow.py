import re
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def get_current_course_link(driver, ignore_urls=None):
    """
    Находит актуальный не пройденный курс.
    Возвращает (course_url, course_name).
    Находит курс со статусом "Проходите сейчас" или "Пересдача",
    пропуская те, что в списке ignore_urls.
    """
    if ignore_urls is None:
        ignore_urls = set()

    status_xpath = (
        "//div[contains(@class,'bcd-curriculum-discipline-state') and "
        "(contains(text(),'Проходите сейчас') or contains(text(),'Пересдача'))]"
    )

    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    status_xpath,
                )
            )
        )

        all_states = driver.find_elements(By.XPATH, status_xpath)

        print(f"🔎 Найдено активных курсов на странице: {len(all_states)}")

        for state_el in all_states:
            try:
                link_el = state_el.find_element(By.XPATH, "./parent::div//a")
                url = link_el.get_attribute("href")
                name = link_el.text.strip()
                state_text = state_el.text.strip()

                print(f"Имя курса: {name}")
                print(f"Статус курса: {state_text}")
                print(f"URL курса: {url}")

                if url not in ignore_urls:
                    return url, name
            except Exception:
                continue

        return None, None
    except Exception:
        return None, None


def find_current_test_info(driver, timeout=20, ignore_test_urls=None):
    """
    Находит первый тест, который нужно пройти:
    - невыполненный
    - незавершенный (есть текущая попытка)
    - выполненный, но не набран проходной балл
    """
    wait = WebDriverWait(driver, timeout)
    ignore_test_urls = ignore_test_urls or set()

    try:
        elem_course = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Элементы курса')]"))
        )
        elem_course.click()

        tests_toggle = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//h3[@id='quiz_overview_title']/preceding-sibling::a"))
        )
        if tests_toggle.get_attribute("aria-expanded") == "false":
            tests_toggle.click()

        wait.until(
            EC.presence_of_element_located((By.XPATH, "//div[@id='quiz_overview']//tr[@data-mdl-overview-cmid]"))
        )
    except Exception as e:
        print(f"❌ Ошибка навигации к тестам: {e}")
        return None, None, None

    rows = driver.find_elements(By.XPATH, "//div[@id='quiz_overview']//tr[@data-mdl-overview-cmid]")
    retry_candidates = []

    for row in rows:
        try:
            completion_td = row.find_element(By.XPATH, ".//td[@data-mdl-overview-item='completion']")
            value = completion_td.get_attribute("data-mdl-overview-value")
            test_name, test_url, topic_name = _extract_test_row_info(row)

            if test_url in ignore_test_urls:
                continue

            if value == "0":
                print(f"✅ Найден тест: {test_name}")
                print(f"📌 Тема лекции: {topic_name} \n")
                return test_name, test_url, topic_name

            retry_candidates.append((test_name, test_url, topic_name))
        except Exception:
            continue

    course_url = driver.current_url

    for test_name, test_url, topic_name in retry_candidates:
        try:
            if _quiz_needs_retry(driver, test_url, timeout=timeout):
                print(f"🔁 Найден тест для перепрохождения: {test_name}")
                print(f"📌 Тема лекции: {topic_name} \n")
                return test_name, test_url, topic_name
        except Exception as e:
            print(f"⚠️ Не удалось проверить тест '{test_name}' на перепрохождение: {e}")
        finally:
            driver.get(course_url)
            time.sleep(1)

    print("Все активные тесты выполнены.")
    return None, None, None


def _extract_test_row_info(row):
    name_el = row.find_element(By.XPATH, ".//a[contains(@class,'activityname')]")
    test_name = name_el.text.strip()
    test_url = name_el.get_attribute("href")

    try:
        topic_el = row.find_element(By.XPATH, ".//div[contains(@class, 'small')]")
        topic_name = topic_el.text.strip()
    except Exception:
        topic_name = None
        print(f"⚠️ Тема для теста '{test_name}' не найдена.")

    return test_name, test_url, topic_name


def _quiz_needs_retry(driver, test_url, timeout=10):
    driver.get(test_url)
    WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    if driver.find_elements(
        By.XPATH,
        "//button[contains(., 'Продолжить текущую попытку')] "
        "| //button[contains(., 'Продолжить последнюю попытку')]",
    ):
        print("↩️ Найдена незавершенная попытка, тест нужно продолжить.")
        return True

    if driver.find_elements(
        By.XPATH,
        "//*[contains(normalize-space(.), 'Не удалось выполнить') and contains(normalize-space(.), 'Получить проходной балл')]",
    ):
        print("📉 Проходной балл не набран, тест нужно перепройти.")
        return True

    page_text = driver.find_element(By.TAG_NAME, "body").text
    pass_grade = _extract_first_number(page_text, r"Проходная оценка:\s*([\d.,]+)")
    best_grade = _extract_first_number(page_text, r"Высшая оценка:\s*([\d.,]+)")

    if pass_grade is not None and best_grade is not None and best_grade < pass_grade:
        print(f"📊 Оценка ниже проходной: {best_grade:.2f} < {pass_grade:.2f}.")
        return True

    return False


def _extract_first_number(text, pattern):
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None

    raw = match.group(1).replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None
