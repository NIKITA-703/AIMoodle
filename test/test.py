from itertools import count
from xml.sax.handler import property_interning_dict

from bs4 import BeautifulSoup

# with open("page_courses.html", encoding="utf-8") as file:
#     src = file.read()

from bs4 import BeautifulSoup
import re


with open("../html/old_page_courses.html", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "lxml")

# 1) найти все ссылки на тесты по URL
quiz_links = soup.find_all(
    "a",
    href=re.compile(r"/mod/quiz/view\.php\?id=\d+")
)

next_quiz = None

for a in quiz_links:
    # 2) подняться к parent <li class="... modtype_quiz ...">
    quiz_li = a.find_parent("li", class_=re.compile(r"\bmodtype_quiz\b"))
    if not quiz_li:
        continue

    # 3) проверить, есть ли внутри span.sr-only с текстом "Надо сделать:"
    if quiz_li.find("span", class_="sr-only", string=re.compile(r"Надо сделать")):
        next_quiz = (quiz_li, a["href"])
        break

if not next_quiz:
    print("Все тесты либо недоступны, либо уже пройдены.")
else:
    quiz_li, url = next_quiz
    # достаём id секции: <li id="section-4"> → "section-4"
    section_li = quiz_li.find_parent("li", id=re.compile(r"^section-\d+$"))
    sec_id = section_li.get("id", "")
    # метод .get("id","") значит: "если есть атрибут id, вернуть его, иначе вернуть ''"
    # потом можно взять число:
    sec_num = int(sec_id.split("-",1)[1]) if sec_id else None

    print(f"Следующий тест в секции {sec_id} (номер {sec_num}):")
    print("URL для перехода:", url)
    # при необходимости можем вывести название:
    print("Название теста:", a.text.strip())



def _():

    with open("../html/output5.html", encoding="utf-8") as file:
        src = file.read()


    soup = BeautifulSoup(src, "lxml")

    find_courses = soup.find_all(class_="section course-section main clearfix")

    # find_courses = soup.find(class_="main-content").find(class_="topics").find_all(class_="availabilityinfo")

    # find_courses = soup.find(class_="main-content").find(class_="topics").find_all(class_="section course-section main clearfix")

    # print(find_courses)

    # count_courses = len(find_courses)
    #
    # print(count_courses)
    #
    # find_actual_test = soup.findParent(class_="availabilityinfo")
    #
    # # for count in range(1, )

    count_courses = len(find_courses)
    print(count_courses)

    # find_actual_test = find_courses[0].find(span="Недоступно, пока не выполнено: Элемент курса")
    # print(find_courses[4])

    # find_actual_test = find_courses[0].find_all(span="Недоступно, пока не выполнено: Элемент курса")

    cors = count_courses[3]

    soup2 = BeautifulSoup(cors.string, "lxml")

    print(soup2.find("Недоступно, пока не выполнено: Элемент курса "))

    # оставляет пустой список а должен найти span вывод типа [block, block, ELEMENT] а выходит прост []

    for item in range(0, count_courses - 1):

        break

        print(f"current ID: {item}")

        find_actual_test = find_courses[item].find_all(span="Недоступно, пока не выполнено: Элемент курса")

        if find_actual_test is not None:
            print(f"ID uncompleted courses: {item}")
            print(find_courses[item])
            break
        else:
            print("None")



