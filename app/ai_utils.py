import json
import os
import re
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from app.config import LM_STUDIO_BASE_URL
from app.lecture_context import build_lecture_context


@dataclass
class AIQuestionResult:
    raw_text: str = ""
    answer_keys: list[str] = field(default_factory=list)
    text_answer: str = ""
    source: str = "general_knowledge"
    evidence: str = ""
    context_mode: str = "none"
    error: str = ""


def _normalize_text(raw_text):
    lines = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if stripped:
            lines.append(" ".join(stripped.split()))
    return "\n".join(lines)


def extract_pdf_text(pdf_path):
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

        clean_text = _normalize_text("\n\n".join(pages_text))
        print(f"   [DEBUG] Текст из PDF сформирован. Длина: {len(clean_text)} символов")
        return clean_text
    except Exception as e:
        print(f"   [DEBUG] ❌ Исключение PDF: {e}")
        return f"❌ Критическая ошибка PDF: {e}"


def clean_html_to_text(file_path):
    print(f"   [DEBUG] Запуск парсинга файла: {os.path.basename(file_path)}")

    if not os.path.exists(file_path):
        return f"❌ ОШИБКА: Файл не найден: {file_path}"
    if file_path.lower().endswith(".pdf"):
        return extract_pdf_text(file_path)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")
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
            ".activity-header",
            ".rui-breadcrumbs",
            ".tertiary-navigation",
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

        main_content = soup.find(id="region-main") or soup.find(role="main") or soup.body
        if not main_content:
            return "❌ Ошибка: Не найден основной контент"

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


def ask_ai_question_data(question, options, lecture_text, question_type="unknown", answer_hint=""):
    url = f"{LM_STUDIO_BASE_URL}/v1/chat/completions"
    lecture_context, context_mode = build_lecture_context(lecture_text, question, options)
    has_lecture = bool(lecture_context)

    system_prompt = (
        "Ты решаешь учебный тест на русском языке. "
        "Если дан контекст лекции, сначала ищи ответ только в нем. "
        "Не показывай рассуждения. Верни только один JSON-объект без markdown.\n"
        "Для вариантов ответа верни: "
        '{"answers":["a"],"text":"","source":"lecture","evidence":"точная короткая цитата"}.\n'
        "Для поля ввода верни: "
        '{"answers":[],"text":"недостающий фрагмент","source":"lecture","evidence":"точная короткая цитата"}.\n'
        "source может быть lecture или general_knowledge. "
        "Ставь lecture только когда ответ подтверждается контекстом и приведи короткую цитату. "
        "Для checkbox допускается несколько букв. Для radio должна быть ровно одна буква. "
        "Текст для поля ввода должен быть в точной грамматической форме без полного предложения."
    )

    options_text = options or "ВАРИАНТОВ НЕТ. Это вопрос на ввод текста."
    hint_block = f"\n### ПОДСКАЗКА ПО ФОРМАТУ:\n{answer_hint}\n" if answer_hint else ""
    lecture_block = lecture_context if has_lecture else "Лекция отсутствует. Разрешено использовать общие знания."

    user_message = f"""
### ТЕКСТ ЛЕКЦИИ:
{lecture_block}

### ВОПРОС:
{question}
{hint_block}
### ТИП ВОПРОСА:
{question_type}

### ВАРИАНТЫ ОТВЕТОВ:
{options_text}

Верни только JSON с итоговым ответом.
"""

    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.1,
        "max_tokens": 1200,
    }

    try:
        response = requests.post(url, json=payload, timeout=180)
        if response.status_code != 200:
            body = response.text.strip()[:300]
            error = f"Ошибка сервера: {response.status_code}"
            if body:
                error += f" | {body}"
            return AIQuestionResult(context_mode=context_mode, error=error)

        raw_content = _extract_chat_content(response.json())
        if not isinstance(raw_content, str) or not raw_content.strip():
            return AIQuestionResult(context_mode=context_mode, error="Пустой ответ LM Studio")

        clean_content = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()
        return _parse_ai_result(clean_content, question_type, lecture_context, context_mode)
    except Exception as e:
        return AIQuestionResult(context_mode=context_mode, error=f"Ошибка соединения: {e}")


def ask_ai_question(question, options, lecture_text, answer_hint=""):
    """Обратная совместимость для старых вспомогательных скриптов."""
    result = ask_ai_question_data(
        question,
        options,
        lecture_text,
        question_type="text" if not options else "unknown",
        answer_hint=answer_hint,
    )
    if result.error:
        return result.error
    if result.raw_text:
        return result.raw_text
    if result.text_answer:
        return result.text_answer
    return ", ".join(result.answer_keys)


def normalize_text_answer(question, raw_answer, answer_hint=""):
    url = f"{LM_STUDIO_BASE_URL}/v1/chat/completions"
    system_prompt = (
        "Тебе дан вопрос с пропуском и сырой ответ модели. "
        "Верни только фрагмент для поля ответа в точной грамматической форме. "
        "Не возвращай полное предложение, пояснения, переводы, скобки и точки."
    )
    user_message = f"""
### ВОПРОС:
{question}

### ПОДСКАЗКА:
{answer_hint or 'Нет'}

### СЫРОЙ ОТВЕТ:
{raw_answer}
"""
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.0,
        "max_tokens": 256,
    }
    fallback = re.sub(r"\s*\([^)]*\)", "", raw_answer).strip().strip('"').strip("'").strip(".")

    try:
        response = requests.post(url, json=payload, timeout=60)
        if response.status_code == 200:
            raw_content = _extract_chat_content(response.json())
            if isinstance(raw_content, str):
                clean = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()
                clean = re.sub(r"\s*\([^)]*\)", "", clean).strip().strip('"').strip("'").strip(".")
                return clean or fallback
    except Exception:
        pass
    return fallback


def check_ai_ready():
    url = f"{LM_STUDIO_BASE_URL}/v1/models"
    try:
        response = requests.get(url, timeout=5)
    except Exception as e:
        return False, f"Локальный ИИ недоступен: {e}"

    if response.status_code != 200:
        body = response.text.strip()[:300]
        message = f"Локальный ИИ ответил ошибкой {response.status_code}"
        return False, f"{message}: {body}" if body else message

    try:
        models = response.json().get("data") or []
    except Exception as e:
        return False, f"Не удалось разобрать ответ локального ИИ: {e}"

    if not models:
        return False, "Локальный ИИ запущен, но ни одна модель не загружена."

    first_model = models[0].get("id") or models[0].get("object") or "unknown"
    return True, f"Локальный ИИ готов. Модель: {first_model}"


def _parse_ai_result(content, question_type, lecture_context, context_mode):
    data = _extract_json_object(content)
    if not data:
        return AIQuestionResult(
            raw_text=content,
            text_answer=content if question_type == "text" else "",
            source="general_knowledge",
            context_mode=context_mode,
        )

    answers = data.get("answers") or []
    if isinstance(answers, str):
        answers = [answers]
    answer_keys = []
    for answer in answers:
        match = re.search(r"\b([a-z0-9]+)\b", str(answer).lower())
        if match and match.group(1) not in answer_keys:
            answer_keys.append(match.group(1))

    evidence = str(data.get("evidence") or "").strip()
    requested_source = str(data.get("source") or "").strip().lower()
    evidence_is_present = _evidence_in_context(evidence, lecture_context)
    source = "lecture" if requested_source == "lecture" and evidence_is_present else "general_knowledge"
    return AIQuestionResult(
        raw_text=content,
        answer_keys=answer_keys,
        text_answer=str(data.get("text") or "").strip(),
        source=source,
        evidence=evidence,
        context_mode=context_mode,
    )


def _extract_json_object(content):
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start : end + 1])
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _evidence_in_context(evidence, context):
    if not evidence or not context:
        return False
    normalized_evidence = re.sub(r"\s+", " ", evidence).strip().lower()
    normalized_context = re.sub(r"\s+", " ", context).lower()
    return len(normalized_evidence) >= 12 and normalized_evidence in normalized_context


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
        text = first_choice.get("text")
        if isinstance(text, str):
            return text
    except Exception:
        return None
    return None
