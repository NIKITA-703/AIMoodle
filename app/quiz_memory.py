import json
import re
from datetime import datetime
from urllib.parse import parse_qs

from selenium.webdriver.common.by import By

from app.config import QUIZ_MEMORY_FILE
from app.quiz_review import QuestionReview, parse_question_reviews


def normalize_question_text(text):
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([?.!,;:])", r"\1", text)
    return text


def extract_question_id(q_block):
    try:
        post_data = q_block.find_element(By.CSS_SELECTOR, ".questionflagpostdata")
        parsed = parse_qs(post_data.get_attribute("value") or "")
        qids = parsed.get("qid") or []
        if qids:
            return str(qids[0])
    except Exception:
        pass

    try:
        inputs = q_block.find_elements(By.CSS_SELECTOR, "input[value*='qid=']")
        for input_el in inputs:
            match = re.search(r"(?:^|&)qid=(\d+)", input_el.get_attribute("value") or "")
            if match:
                return match.group(1)
    except Exception:
        pass

    return ""


def load_quiz_memory():
    if not QUIZ_MEMORY_FILE.exists():
        return {"version": 2, "scopes": {}}

    try:
        with open(QUIZ_MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "scopes" in data:
                data.setdefault("version", 1)
                return data
    except Exception:
        pass

    return {"version": 2, "scopes": {}}


def save_quiz_memory(memory):
    memory["version"] = 2
    with open(QUIZ_MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def get_confirmed_answer(
    course_name,
    test_name,
    question_text,
    course_id="",
    quiz_id="",
    question_id="",
):
    memory = load_quiz_memory()
    scopes = memory.get("scopes", {})

    scope_keys = [_scope_key(course_id, quiz_id, course_name, test_name)]
    legacy_scope = f"{(course_name or '').strip()}|||{(test_name or '').strip()}"
    if legacy_scope not in scope_keys:
        scope_keys.append(legacy_scope)

    question_keys = [_question_key(question_id, question_text)]
    normalized_text = normalize_question_text(question_text)
    for fallback in (f"text:{normalized_text}", normalized_text):
        if fallback not in question_keys:
            question_keys.append(fallback)

    for scope_key in scope_keys:
        questions = scopes.get(scope_key, {}).get("questions", {})
        for question_key in question_keys:
            confirmed = questions.get(question_key, {}).get("confirmed_answer")
            if confirmed:
                return confirmed

    return None

def record_review_results(driver, course_name, test_name, course_id="", quiz_id=""):
    reviews = parse_question_reviews(driver.page_source)
    memory = load_quiz_memory()
    scopes = memory.setdefault("scopes", {})
    scope_key = _scope_key(course_id, quiz_id, course_name, test_name)
    scope = scopes.setdefault(
        scope_key,
        {
            "course_id": str(course_id or ""),
            "quiz_id": str(quiz_id or ""),
            "course_name": course_name,
            "test_name": test_name,
            "updated_at": "",
            "questions": {},
        },
    )
    questions_store = scope.setdefault("questions", {})

    saved_count = 0
    confirmed_count = 0
    new_confirmed_count = 0

    for review in reviews:
        question_key = _question_key(review.question_id, review.question_text)
        existing = questions_store.get(question_key, {})
        attempts = list(existing.get("attempts", []))
        attempts.append(_attempt_payload(review))
        attempts = attempts[-10:]

        confirmed_answer = _build_confirmed_answer(review)
        payload = {
            "question_id": review.question_id,
            "question_text": review.question_text,
            "question_type": review.question_type,
            "options": [option.__dict__ for option in review.options],
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "attempts": attempts,
        }

        if confirmed_answer:
            payload["confirmed_answer"] = confirmed_answer
            confirmed_count += 1
            if not existing.get("confirmed_answer"):
                new_confirmed_count += 1
        elif existing.get("confirmed_answer"):
            payload["confirmed_answer"] = existing["confirmed_answer"]

        questions_store[question_key] = payload
        saved_count += 1

    scope["updated_at"] = datetime.now().isoformat(timespec="seconds")
    save_quiz_memory(memory)
    print(
        f"🧠 Память теста обновлена: {saved_count} вопросов, "
        f"подтверждено {confirmed_count}, новых {new_confirmed_count}."
    )
    return {
        "saved_count": saved_count,
        "confirmed_count": confirmed_count,
        "new_confirmed_count": new_confirmed_count,
    }


def _scope_key(course_id, quiz_id, course_name, test_name):
    if course_id or quiz_id:
        return f"course:{course_id or 'unknown'}|quiz:{quiz_id or 'unknown'}"
    return f"{(course_name or '').strip()}|||{(test_name or '').strip()}"


def _question_key(question_id, question_text):
    if question_id:
        return f"qid:{question_id}"
    return f"text:{normalize_question_text(question_text)}"


def _attempt_payload(review):
    return {
        "score": review.score,
        "max_score": review.max_score,
        "selected_keys": [item.key for item in review.selected_options],
        "selected_texts": [item.text for item in review.selected_options],
        "text_answer": review.text_answer,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
    }


def _build_confirmed_answer(review: QuestionReview):
    if review.score is None or review.max_score is None or review.max_score <= 0:
        return None

    is_full = abs(review.score - review.max_score) < 1e-9
    is_zero = abs(review.score) < 1e-9
    selected = review.selected_options

    if review.question_type == "text":
        if is_full and review.text_answer:
            return {"type": "text", "text": review.text_answer, "source": "full_score"}
        return None

    if review.question_type in {"radio", "select"} and is_full and selected:
        return {
            "type": review.question_type,
            "keys": [selected[0].key],
            "texts": [selected[0].text],
            "source": "full_score",
        }

    if review.question_type == "radio" and is_zero and len(review.options) == 2 and len(selected) == 1:
        other = [option for option in review.options if option.key != selected[0].key]
        if other:
            return {
                "type": "radio",
                "keys": [other[0].key],
                "texts": [other[0].text],
                "source": "binary_inverse",
            }

    if review.question_type == "checkbox" and is_full:
        return {
            "type": "checkbox",
            "keys": [item.key for item in selected],
            "texts": [item.text for item in selected],
            "source": "full_score",
        }

    return None
