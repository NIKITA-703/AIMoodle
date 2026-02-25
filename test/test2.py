from bs4 import BeautifulSoup
import re

with open("../html/old_page_courses.html", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "lxml")

# 1) находим все ссылки на тесты
quiz_links = soup.find_all(
    "a",
    href=re.compile(r"/mod/quiz/view\.php\?id=\d+")
)

next_quiz = None

for a in quiz_links:
    # 2) поднимаемся к блоку <li class="modtype_quiz ...">
    quiz_li = a.find_parent("li", class_=re.compile(r"\bmodtype_quiz\b"))
    if not quiz_li:
        continue

    # 3) ищем фразу "Надо сделать:"
    if quiz_li.find("span", class_="sr-only", string=re.compile(r"Надо сделать")):
        next_quiz = (quiz_li, a)
        break

if not next_quiz:
    print("Все тесты либо недоступны, либо уже пройдены.")
else:
    quiz_li, a = next_quiz

    # 4) ищем секцию section-XX
    section_li = quiz_li.find_parent("li", id=re.compile(r"^section-\d+$"))
    sec_id = section_li.get("id", "")
    sec_num = int(sec_id.split("-")[1]) if sec_id else None

    # 5) достаём название теста
    title_el = a.find("span", class_="instancename")
    title = title_el.get_text(strip=True) if title_el else a.get_text(strip=True)

    print(f"Следующий тест в секции {sec_id} (номер {sec_num}):")
    print("URL для перехода:", a["href"])
    print("Название теста:", title)
# ------
def find_next_quiz(driver):
    """
    Находит первый тест, который надо выполнить ("completion_incomplete")
    и возвращает (название, ссылка).
    """

    # ждём загрузки списка тестов
    WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li[id*='course-index-cm']"))
    )

    # получаем все элементы li с тестами
    items = driver.find_elements(By.CSS_SELECTOR, "li[id*='course-index-cm-']")

    for li in items:

        # ищем индикатор "надо сделать" (completion_incomplete)
        try:
            li.find_element(By.CSS_SELECTOR, ".completion_incomplete")
        except:
            continue  # если не найден — тест выполнен → пропускаем

        # если нашли completion_incomplete → значит это нужный тест
        try:
            link_el = li.find_element(By.CSS_SELECTOR, "a.courseindex-link")
            test_url = link_el.get_attribute("href")
            test_name = link_el.text.strip()
        except:
            test_url = None
            test_name = None

        return test_name, test_url

    return None, None


"""
откроет ресурсы лекции
https://lms.mitu.msk.ru/course/overview.php?id=83

# 2️⃣ Разворачиваем блок с тестами
    tests_toggle = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, "//div[contains(., 'Тесты')]//a[contains(@class, 'icons-collapse-expand')]")
        )
    )


"""