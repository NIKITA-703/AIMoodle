from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


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

