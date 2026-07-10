import json
import re
from datetime import datetime

from selenium.webdriver.common.by import By

from app.config import QUIZ_MEMORY_FILE


def normalize_question_text(text):
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def load_quiz_memory():
    if not QUIZ_MEMORY_FILE.exists():
        return {"scopes": {}}

    try:
        with open(QUIZ_MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "scopes" in data:
                return data
    except Exception:
        pass

    return {"scopes": {}}


def save_quiz_memory(memory):
    with open(QUIZ_MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def _scope_key(course_name, test_name):
    return f"{(course_name or '').strip()}|||{(test_name or '').strip()}"


def get_confirmed_answer(course_name, test_name, question_text):
    memory = load_quiz_memory()
    scope = memory.get("scopes", {}).get(_scope_key(course_name, test_name), {})
    question = scope.get("questions", {}).get(normalize_question_text(question_text), {})
    return question.get("confirmed_answer")


def record_review_results(driver, course_name, test_name):
    memory = load_quiz_memory()
    scopes = memory.setdefault("scopes", {})
    scope = scopes.setdefault(
        _scope_key(course_name, test_name),
        {
            "course_name": course_name,
            "test_name": test_name,
            "updated_at": "",
            "questions": {},
        },
    )
    questions_store = scope.setdefault("questions", {})

    question_blocks = driver.find_elements(By.CSS_SELECTOR, ".que")
    saved_count = 0
    confirmed_count = 0

    for q_block in question_blocks:
        try:
            record = _parse_review_question(q_block)
            if not record:
                continue

            q_key = normalize_question_text(record["question_text"])
            if not q_key:
                continue

            existing = questions_store.get(q_key, {})
            attempts = existing.get("attempts", [])
            attempts.append(record["attempt"])
            if len(attempts) > 10:
                attempts = attempts[-10:]

            payload = {
                "question_text": record["question_text"],
                "question_type": record["question_type"],
                "options": record["options"],
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "attempts": attempts,
            }

            if record.get("confirmed_answer"):
                payload["confirmed_answer"] = record["confirmed_answer"]
                confirmed_count += 1
            elif existing.get("confirmed_answer"):
                payload["confirmed_answer"] = existing["confirmed_answer"]

            questions_store[q_key] = payload
            saved_count += 1
        except Exception:
            continue

    scope["updated_at"] = datetime.now().isoformat(timespec="seconds")
    save_quiz_memory(memory)
    print(f"🧠 Память теста обновлена: {saved_count} вопросов, подтверждено {confirmed_count}.")


def _parse_review_question(q_block):
    q_text = q_block.find_element(By.CSS_SELECTOR, ".qtext").text.strip()
    question_type = _detect_question_type(q_block)
    score, max_score = _parse_grade_text(q_block)

    options = []
    selected_options = []
    text_answer = ""

    if question_type == "text":
        try:
            text_input = q_block.find_element(By.CSS_SELECTOR, "input[type='text']")
            text_answer = (text_input.get_attribute("value") or "").strip()
        except Exception:
            text_answer = ""
    else:
        for index, opt in enumerate(q_block.find_elements(By.CSS_SELECTOR, ".answer div[class^='r']")):
            try:
                label_text = opt.text.strip()
                key = ""
                try:
                    key = opt.find_element(By.CSS_SELECTOR, ".answernumber").text.lower().strip(" .)")
                except Exception:
                    key = f"opt_{index}"

                input_el = opt.find_element(By.CSS_SELECTOR, "input")
                checked = input_el.is_selected()

                option_payload = {
                    "key": key,
                    "text": label_text,
                    "checked": checked,
                }
                options.append(option_payload)
                if checked:
                    selected_options.append(option_payload)
            except Exception:
                continue

    attempt = {
        "score": score,
        "max_score": max_score,
        "selected_keys": [item["key"] for item in selected_options],
        "selected_texts": [item["text"] for item in selected_options],
        "text_answer": text_answer,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
    }

    confirmed_answer = _build_confirmed_answer(question_type, options, selected_options, text_answer, score, max_score)

    return {
        "question_text": q_text,
        "question_type": question_type,
        "options": options,
        "attempt": attempt,
        "confirmed_answer": confirmed_answer,
    }


def _detect_question_type(q_block):
    if q_block.find_elements(By.CSS_SELECTOR, "input[type='text']"):
        return "text"
    if q_block.find_elements(By.TAG_NAME, "select"):
        return "select"
    if q_block.find_elements(By.CSS_SELECTOR, "input[type='checkbox']"):
        return "checkbox"
    if q_block.find_elements(By.CSS_SELECTOR, "input[type='radio']"):
        return "radio"
    return "unknown"


def _parse_grade_text(q_block):
    try:
        grade_text = q_block.find_element(By.CSS_SELECTOR, ".grade").text.strip()
    except Exception:
        return None, None

    match = re.search(r"([\d.,]+)\s+из\s+([\d.,]+)", grade_text)
    if not match:
        return None, None

    return _to_float(match.group(1)), _to_float(match.group(2))


def _to_float(value):
    try:
        return float(str(value).replace(" ", "").replace(",", "."))
    except Exception:
        return None


def _build_confirmed_answer(question_type, options, selected_options, text_answer, score, max_score):
    if score is None or max_score is None:
        return None

    if max_score <= 0:
        return None

    is_full = abs(score - max_score) < 1e-9
    is_zero = abs(score) < 1e-9

    if question_type == "text":
        if is_full and text_answer:
            return {
                "type": "text",
                "text": text_answer,
                "source": "full_score",
            }
        return None

    if question_type == "select":
        if is_full and selected_options:
            return {
                "type": "select",
                "keys": [selected_options[0]["key"]],
                "texts": [selected_options[0]["text"]],
                "source": "full_score",
            }
        return None

    if question_type == "radio":
        if is_full and selected_options:
            return {
                "type": "radio",
                "keys": [selected_options[0]["key"]],
                "texts": [selected_options[0]["text"]],
                "source": "full_score",
            }

        if is_zero and len(options) == 2 and len(selected_options) == 1:
            other = [item for item in options if item["key"] != selected_options[0]["key"]]
            if other:
                return {
                    "type": "radio",
                    "keys": [other[0]["key"]],
                    "texts": [other[0]["text"]],
                    "source": "binary_inverse",
                }
        return None

    if question_type == "checkbox":
        if is_full:
            return {
                "type": "checkbox",
                "keys": [item["key"] for item in selected_options],
                "texts": [item["text"] for item in selected_options],
                "source": "full_score",
            }
        return None

    return None
