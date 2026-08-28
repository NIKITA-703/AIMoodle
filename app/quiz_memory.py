import json
import os
import re
import threading
from datetime import datetime
from functools import wraps
from urllib.parse import parse_qs, urlparse

from selenium.webdriver.common.by import By

from app.config import QUIZ_MEMORY_FILE
from app.quiz_review import QuestionReview, parse_question_reviews


_MEMORY_LOCK = threading.RLock()


def _with_memory_lock(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        with _MEMORY_LOCK:
            return func(*args, **kwargs)

    return wrapper


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


@_with_memory_lock
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


@_with_memory_lock
def save_quiz_memory(memory):
    memory["version"] = 2
    temp_path = QUIZ_MEMORY_FILE.with_suffix(f"{QUIZ_MEMORY_FILE.suffix}.tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, QUIZ_MEMORY_FILE)


@_with_memory_lock
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


@_with_memory_lock
def get_review_feedback(
    course_name,
    test_name,
    question_text,
    course_id="",
    quiz_id="",
    question_id="",
    limit=3,
):
    """Return recent non-full results for another attempt of this question."""
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
            attempts = [
                attempt
                for attempt in questions.get(question_key, {}).get("attempts", [])
                if _is_non_full_attempt(attempt)
            ]
            if attempts:
                return attempts[-max(1, int(limit or 1)):]
    return []


@_with_memory_lock
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
    attempt_id = _review_attempt_id(driver)
    captured_attempt_ids = scope.setdefault("captured_attempt_ids", [])
    if attempt_id and attempt_id in captured_attempt_ids:
        print(f"⏭️ Попытка {attempt_id} уже сохранена в памяти.")
        return {
            "saved_count": 0,
            "confirmed_count": 0,
            "new_confirmed_count": 0,
            "already_captured": True,
        }
    questions_store = scope.setdefault("questions", {})

    saved_count = 0
    confirmed_count = 0
    new_confirmed_count = 0
    status_counts = {
        "correct": 0,
        "partial": 0,
        "incorrect": 0,
        "not_answered": 0,
        "unknown": 0,
    }

    for review in reviews:
        status_counts[review.status if review.status in status_counts else "unknown"] += 1
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

    if attempt_id and reviews:
        captured_attempt_ids.append(attempt_id)
        scope["captured_attempt_ids"] = captured_attempt_ids[-20:]
    scope["updated_at"] = datetime.now().isoformat(timespec="seconds")
    save_quiz_memory(memory)
    print(
        f"🧠 Память теста обновлена: {saved_count} вопросов, "
        f"подтверждено {confirmed_count}, новых {new_confirmed_count}."
    )
    if reviews:
        print(
            f"📋 Обзор: {status_counts['correct']} верных, "
            f"{status_counts['partial']} частичных, "
            f"{status_counts['incorrect']} неверных, "
            f"{status_counts['not_answered']} без ответа."
        )
    return {
        "saved_count": saved_count,
        "confirmed_count": confirmed_count,
        "new_confirmed_count": new_confirmed_count,
        "already_captured": False,
        "status_counts": status_counts,
    }


def _review_attempt_id(driver):
    try:
        values = parse_qs(urlparse(driver.current_url).query).get("attempt") or []
        return str(values[0]) if values else ""
    except Exception:
        return ""


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
        "status": review.status,
        "score": review.score,
        "max_score": review.max_score,
        "selected_keys": [item.key for item in review.selected_options],
        "selected_texts": [item.text for item in review.selected_options],
        "correct_keys": [item.key for item in review.options if item.correct is True],
        "incorrect_keys": [item.key for item in review.options if item.correct is False],
        "correct_texts": [item.text for item in review.options if item.correct is True],
        "incorrect_texts": [item.text for item in review.options if item.correct is False],
        "text_answer": review.text_answer,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
    }


def _is_non_full_attempt(attempt):
    score = attempt.get("score")
    max_score = attempt.get("max_score")
    if score is None or max_score is None or max_score <= 0:
        return attempt.get("status") in {"partial", "incorrect", "not_answered"}
    return score + 1e-9 < max_score


def _build_confirmed_answer(review: QuestionReview):
    explicitly_correct = [item for item in review.options if item.correct is True]
    has_score = review.score is not None and review.max_score is not None and review.max_score > 0
    is_full = has_score and abs(review.score - review.max_score) < 1e-9
    is_zero = has_score and abs(review.score) < 1e-9
    is_fully_correct = is_full or review.status == "correct"
    selected = review.selected_options

    # A radio question has one correct choice, so explicit Moodle feedback is conclusive.
    if review.question_type in {"radio", "select"} and explicitly_correct:
        return {
            "type": review.question_type,
            "keys": [explicitly_correct[0].key],
            "texts": [explicitly_correct[0].text],
            "source": "review_feedback",
        }

    # In a partial checkbox review Moodle may mark only the selected correct choices.
    # Such a subset must never replace a previously confirmed complete answer.
    if review.question_type == "checkbox" and is_fully_correct and explicitly_correct:
        return {
            "type": "checkbox",
            "keys": [item.key for item in explicitly_correct],
            "texts": [item.text for item in explicitly_correct],
            "source": "review_feedback",
        }

    if not has_score:
        return None

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

    if review.question_type == "checkbox" and is_fully_correct:
        return {
            "type": "checkbox",
            "keys": [item.key for item in selected],
            "texts": [item.text for item in selected],
            "source": "full_score",
        }

    return None
