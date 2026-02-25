import requests
import json
import os
import re

from bs4 import BeautifulSoup


def clean_html_to_text(html_path):
    """
    Парсит HTML, чистит мусор и возвращает текст.
    Версия с отладкой (Debug).
    """
    print(f"   [DEBUG] Запуск парсинга файла: {os.path.basename(html_path)}")

    if not os.path.exists(html_path):
        return f"❌ ОШИБКА: Файл не найден: {html_path}"

    try:
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Используем 'html.parser' (он встроен в Python, lxml может требовать установки)
        soup = BeautifulSoup(html_content, "html.parser")
        print("   [DEBUG] HTML загружен в BeautifulSoup")

        # 1. Удаляем мусор
        garbage_selectors = [
            "script", "style", "noscript", "iframe",
            "nav", "footer", "header", "form",
            ".activity-navigation", ".urlselect",
            ".rui-activity-header", "#block-region-side-pre",
        ]

        count_deleted = 0
        for selector in garbage_selectors:
            for tag in soup.select(selector):
                tag.decompose()
                count_deleted += 1
        print(f"   [DEBUG] Удалено мусорных блоков: {count_deleted}")

        # 2. Ищем контент
        main_content = soup.find(id="region-main")
        if not main_content:
            main_content = soup.find(role="main")
        if not main_content:
            main_content = soup.body

        if not main_content:
            print("   [DEBUG] ❌ Не нашли region-main, role=main или body")
            return "❌ Ошибка: Не найден основной контент"

        print("   [DEBUG] Основной контент найден. Разворачиваем теги...")

        # 3. Разворачиваем теги (убираем жирный/курсив, оставляем текст)
        inline_tags = ["b", "strong", "i", "em", "u", "span", "a", "font", "mark", "small"]
        for tag_name in inline_tags:
            for tag in main_content.find_all(tag_name):
                tag.unwrap()

        # 4. Достаем текст
        raw_text = main_content.get_text(separator='\n')

        # 5. Чистим строки
        lines = []
        for line in raw_text.splitlines():
            stripped = line.strip()
            if stripped:
                clean_line = " ".join(stripped.split())
                lines.append(clean_line)

        clean_text = '\n'.join(lines)

        print(f"   [DEBUG] Текст сформирован. Длина: {len(clean_text)} символов")

        # !!! ВОТ САМОЕ ВАЖНОЕ !!!
        return clean_text

    except Exception as e:
        print(f"   [DEBUG] ❌ Исключение: {e}")
        return f"❌ Критическая ошибка: {e}"


def save_text_file(text, html_path):
    try:
        txt_path = os.path.splitext(html_path)[0] + ".txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"💾 Файл сохранен: {txt_path}")
        return txt_path
    except Exception as e:
        print(f"❌ Ошибка сохранения: {e}")
        return None


def ask_ai_question(question, options, lecture_text):
    """
    Отправляет запрос в LM Studio.
    Обрабатывает ответы "думающих" моделей.
    """
    url = "http://localhost:1234/v1/chat/completions"

    # 1. Улучшенный Промпт
    # Мы явно требуем JSON или строгий формат, чтобы модель не болтала лишнего после раздумий.
    system_prompt = (
        "Ты — русскоязычный студент, сдающий экзамен. "
        "Твоя задача — выбрать правильный ответ на основе лекции.\n"
        "ИНСТРУКЦИЯ:\n"
        "1. Сначала подумай, но выводи ответ строго в конце.\n"
        "2. Твой финальный ответ должен быть на РУССКОМ языке.\n"
        "3. Формат финального ответа: ТОЛЬКО буква и текст варианта (например: 'a. ответ')."
    )

    # Ограничим лекцию, чтобы оставить место для ответа
    # (Учитывая, что ты увеличил контекст в LM Studio до 12k+, тут можно ставить много)
    context_limit = 20000

    user_message = f"""
### ТЕКСТ ЛЕКЦИИ:
{lecture_text[:context_limit]}

### ВОПРОС:
{question}

### ВАРИАНТЫ ОТВЕТОВ:
{options}

Какой вариант правильный?
"""

    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.1,
        # ВАЖНО: Увеличиваем лимит, чтобы модель успела "подумать" и написать ответ
        "max_tokens": 1500
    }

    try:
        response = requests.post(url, json=payload, timeout=180)  # Таймаут побольше
        if response.status_code == 200:
            result = response.json()
            raw_content = result['choices'][0]['message']['content']

            # --- МАГИЯ ОЧИСТКИ ОТВЕТА ---

            # 1. Удаляем блоки <think>...</think> (если они есть)
            clean_content = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()

            # 2. Если модель написала много текста, пробуем найти последнюю строку (обычно там ответ)
            # Или просто возвращаем очищенный текст, так как промпт просил краткости
            return clean_content

        else:
            return f"Ошибка сервера: {response.status_code}"
    except Exception as e:
        return f"Ошибка соединения: {e}"


if __name__ == "__main__":
    # Тестовый запуск
    base_dir = os.path.join(os.getcwd(), "HTML Courses", "Операционные системы ч.1")

    print(f"📂 Папка: {base_dir}")

    if os.path.exists(base_dir):
        files = [f for f in os.listdir(base_dir) if f.endswith(".html")]
        if files:
            latest_file = max([os.path.join(base_dir, f) for f in files], key=os.path.getctime)
            print(f"📄 Файл: {os.path.basename(latest_file)}")

            # Вызов функции
            result_text = clean_html_to_text(latest_file)

            # Проверка результата
            if result_text is None:
                print("😱 ОШИБКА: Функция вернула None! (Проверь return)")
            elif result_text.startswith("❌"):
                print(f"Ошибка внутри функции: {result_text}")
            elif result_text == "":
                print("⚠️ Предупреждение: Текст пустой (возможно, лекция пустая?)")
            else:
                save_text_file(result_text, latest_file)
                print("✅ УСПЕХ! Текст получен и сохранен.")
        else:
            print("Нет HTML файлов.")
    else:
        print("Папка не найдена.")

