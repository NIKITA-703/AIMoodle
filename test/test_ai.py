import os
from app.ai_utils import ask_ai_question


# должен находится вместе с файлом ai_utils

# 1. Загружаем текст лекции, который мы спарсили
# Укажи здесь имя файла .txt, который создался на прошлом шаге
lecture_filename = "Операционные системы ч.1_ Тема 2. Процессы в операционной системе _ МИТУ.txt"
# Путь может отличаться, проверь папку
base_dir = os.path.join(os.getcwd(), "HTML Courses", "Операционные системы ч.1")
lecture_path = os.path.join(base_dir, lecture_filename)

lecture_text = ""
if os.path.exists(lecture_path):
    with open(lecture_path, "r", encoding="utf-8") as f:
        lecture_text = f.read()
    print(f"✅ Лекция загружена: {len(lecture_text)} символов.\n")
else:
    print(f"❌ Файл лекции не найден: {lecture_path}")
    # Для теста, если файла нет, попробуем без лекции (на общих знаниях)
    lecture_text = "Текст лекции отсутствует."

# 2. Список вопросов (из твоего примера)
questions = [
    {
        "q": "Процесс-родитель приостанавливает свое выполнение посредством функции ...",
        "opts": "a. extermination()\nb. wait()\nc. kill()"
    },
    {
        "q": "Уникальный идентификатор процесса:",
        "opts": "a. pid\nb. pod\nc. pyd\nd. pud"
    },
    {
        "q": "Если свободных ресурсов недостаточно, то вызов fork() завершается неудачно. Верно ли утверждение?",
        "opts": "a. да\nb. нет"
    },
    {
        "q": "При создании каждого процесса создается некоторая структура данных, называемая ...",
        "opts": "a. PCT\nb. PCP\nc. PCB\nd. PSP"
    },
    {
        "q": "... процессы имеют доступ только к собственным инструкциям и области памяти.",
        "opts": "a. в режиме задачи\nb. в режиме ядра"
    },
    {
        "q": "Процесс блокирован и ожидает некоторого события:",
        "opts": "a. Executing\nb. Interruptible\nc. Stopped\nd. Zombie"
    },
    {
        "q": "Context switch:",
        "opts": "a. переформатирование контекста\nb. переключение контекста\nc. изменение контекста"
    }
]

# 3. Прогоняем тест
print("🚀 Начинаем тестирование ИИ...\n")

for i, item in enumerate(questions, 1):
    print(f"--- Вопрос {i} ---")
    print(f"❓ {item['q']}")

    # Спрашиваем ИИ
    answer = ask_ai_question(item['q'], item['opts'], lecture_text)

    print(f"🤖 Ответ ИИ: {answer}")
    print("-" * 40)