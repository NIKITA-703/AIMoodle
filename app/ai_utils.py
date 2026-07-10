import os
import re

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader


def _normalize_text(raw_text):
    lines = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if stripped:
            clean_line = " ".join(stripped.split())
            lines.append(clean_line)
    return "\n".join(lines)


def extract_pdf_text(pdf_path):
    """
    Извлекает текст из PDF и возвращает очищенную строку.
    """
    print(f"   [DEBUG] Запуск парсинга PDF: {os.path.basename(pdf_path)}")

    if not os.path.exists(pdf_path):
        return f"❌ ОШИБКА: Файл не найден: {pdf_path}"

    try:
        reader = PdfReader(pdf_path)
        pages_text = []

        for index, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    pages_text.append(page_text)
            except Exception as e:
                print(f"   [DEBUG] Ошибка чтения страницы PDF {index}: {e}")

        clean_text = _normalize_text("\n".join(pages_text))
        print(f"   [DEBUG] Текст из PDF сформирован. Длина: {len(clean_text)} символов")
        return clean_text
    except Exception as e:
        print(f"   [DEBUG] ❌ Исключение PDF: {e}")
        return f"❌ Критическая ошибка PDF: {e}"


def clean_html_to_text(file_path):
    """
    Парсит HTML или PDF, чистит мусор и возвращает текст.
    """
    print(f"   [DEBUG] Запуск парсинга файла: {os.path.basename(file_path)}")

    if not os.path.exists(file_path):
        return f"❌ ОШИБКА: Файл не найден: {file_path}"

    if file_path.lower().endswith(".pdf"):
        return extract_pdf_text(file_path)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        soup = BeautifulSoup(html_content, "html.parser")
        print("   [DEBUG] HTML загружен в BeautifulSoup")

        garbage_selectors = [
            "script",
            "style",
            "noscript",
            "iframe",
            "nav",
            "footer",
            "header",
            "form",
            ".activity-navigation",
            ".urlselect",
            ".rui-activity-header",
            "#block-region-side-pre",
        ]

        count_deleted = 0
        for selector in garbage_selectors:
            for tag in soup.select(selector):
                tag.decompose()
                count_deleted += 1
        print(f"   [DEBUG] Удалено мусорных блоков: {count_deleted}")

        main_content = soup.find(id="region-main")
        if not main_content:
            main_content = soup.find(role="main")
        if not main_content:
            main_content = soup.body

        if not main_content:
            print("   [DEBUG] ❌ Не нашли region-main, role=main или body")
            return "❌ Ошибка: Не найден основной контент"

        print("   [DEBUG] Основной контент найден. Разворачиваем теги...")

        inline_tags = ["b", "strong", "i", "em", "u", "span", "a", "font", "mark", "small"]
        for tag_name in inline_tags:
            for tag in main_content.find_all(tag_name):
                tag.unwrap()

        clean_text = _normalize_text(main_content.get_text(separator="\n"))

        print(f"   [DEBUG] Текст сформирован. Длина: {len(clean_text)} символов")
        return clean_text
    except Exception as e:
        print(f"   [DEBUG] ❌ Исключение: {e}")
        return f"❌ Критическая ошибка: {e}"


def save_text_file(text, source_path):
    try:
        txt_path = os.path.splitext(source_path)[0] + ".txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"💾 Файл сохранен: {txt_path}")
        return txt_path
    except Exception as e:
        print(f"❌ Ошибка сохранения: {e}")
        return None


def is_context_error_text(text):
    return bool(text) and text.lstrip().startswith("❌")


def is_ai_error_text(text):
    if not text:
        return False

    lowered = text.lower()
    return (
        lowered.startswith("ошибка сервера:")
        or lowered.startswith("ошибка соединения:")
        or "no models loaded" in lowered
        or "failed to fetch" in lowered
    )


def _extract_chat_content(result):
    try:
        choices = result.get("choices") or []
        if not choices:
            return None

        first_choice = choices[0] or {}
        message = first_choice.get("message") or {}
        content = message.get("content")

        if isinstance(content, str):
            return content

        alt_text = first_choice.get("text")
        if isinstance(alt_text, str):
            return alt_text

        delta = first_choice.get("delta") or {}
        delta_content = delta.get("content")
        if isinstance(delta_content, str):
            return delta_content
    except Exception:
        return None

    return None


def ask_ai_question(question, options, lecture_text, answer_hint=""):
    """
    Отправляет запрос в LM Studio.
    """
    url = "http://localhost:1234/v1/chat/completions"

    system_prompt = (
        "Ты — русскоязычный студент, сдающий экзамен. "
        "Твоя задача — выбрать правильный ответ на основе лекции.\n"
        "ИНСТРУКЦИЯ:\n"
        "1. Сначала подумай, но выводи ответ строго в конце.\n"
        "2. Твой финальный ответ должен быть на РУССКОМ языке.\n"
        "3. Если это тест с вариантами, формат финального ответа: ТОЛЬКО буква и текст варианта "
        "(например: 'a. ответ').\n"
        "4. Если это вопрос на ввод текста, верни только недостающий фрагмент в точной грамматической форме, "
        "чтобы его можно было сразу подставить в пропуск. Не повторяй весь вопрос, не добавляй пояснений, "
        "скобок, перевода и точек."
    )

    context_limit = 20000

    if not options or options.strip() == "":
        options_text = "ВАРИАНТОВ НЕТ. Это вопрос на ввод текста. Впиши пропущенное слово или ответ."
    else:
        options_text = options

    hint_block = f"\n### ПОДСКАЗКА ПО ФОРМАТУ:\n{answer_hint}\n" if answer_hint else ""

    user_message = f"""
### ТЕКСТ ЛЕКЦИИ:
{lecture_text[:context_limit]}

### ВОПРОС:
{question}
{hint_block}
### ВАРИАНТЫ ОТВЕТОВ:
{options_text}

Какой вариант правильный?
"""

    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.1,
        "max_tokens": 1500,
    }

    try:
        response = requests.post(url, json=payload, timeout=180)
        if response.status_code == 200:
            result = response.json()
            raw_content = _extract_chat_content(result)
            if not isinstance(raw_content, str):
                print("   [DEBUG] Пустой или нестандартный ответ LM Studio в ask_ai_question")
                return ""
            clean_content = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()
            return clean_content
        error_body = response.text.strip()
        if error_body:
            error_body = error_body[:300]
            return f"Ошибка сервера: {response.status_code} | {error_body}"
        return f"Ошибка сервера: {response.status_code}"
    except Exception as e:
        return f"Ошибка соединения: {e}"


def normalize_text_answer(question, raw_answer, answer_hint=""):
    """
    Сжимает сырой ответ модели до точного фрагмента для поля ввода.
    """
    url = "http://localhost:1234/v1/chat/completions"

    system_prompt = (
        "Тебе дан вопрос с пропуском и сырой ответ модели. "
        "Верни только тот фрагмент, который нужно вставить в поле ответа. "
        "Сохрани точную грамматическую форму. "
        "Если по подсказке нужен один пропуск, верни только одно слово. "
        "Не возвращай полное предложение, пояснения, переводы, скобки и точки."
    )

    user_message = f"""
### ВОПРОС:
{question}

### ПОДСКАЗКА:
{answer_hint or 'Нет'}

### СЫРОЙ ОТВЕТ:
{raw_answer}

Верни только итоговый фрагмент для вставки в пропуск.
"""

    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.0,
        "max_tokens": 256,
    }

    fallback = re.sub(r"\s*\([^)]*\)", "", raw_answer).strip()
    fallback = fallback.strip('"').strip("'").strip(".")

    try:
        response = requests.post(url, json=payload, timeout=60)
        if response.status_code == 200:
            result = response.json()
            raw_content = _extract_chat_content(result)
            if not isinstance(raw_content, str):
                print("   [DEBUG] Пустой или нестандартный ответ LM Studio в normalize_text_answer")
                return fallback
            clean_content = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()
            clean_content = re.sub(r"\s*\([^)]*\)", "", clean_content).strip()
            clean_content = clean_content.strip('"').strip("'").strip(".")
            return clean_content or fallback
    except Exception:
        pass

    return fallback


def check_ai_ready():
    """
    Проверяет, доступен ли локальный OpenAI-compatible сервер
    и загружена ли в нем хотя бы одна модель.
    Возвращает (is_ready, message).
    """
    url = "http://localhost:1234/v1/models"

    try:
        response = requests.get(url, timeout=5)
    except Exception as e:
        return False, f"Локальный ИИ недоступен: {e}"

    if response.status_code != 200:
        body = response.text.strip()[:300]
        if body:
            return False, f"Локальный ИИ ответил ошибкой {response.status_code}: {body}"
        return False, f"Локальный ИИ ответил ошибкой {response.status_code}"

    try:
        payload = response.json()
    except Exception as e:
        return False, f"Не удалось разобрать ответ локального ИИ: {e}"

    models = payload.get("data") or []
    if not models:
        return False, "Локальный ИИ запущен, но ни одна модель не загружена."

    first_model = models[0].get("id") or models[0].get("object") or "unknown"
    return True, f"Локальный ИИ готов. Модель: {first_model}"
