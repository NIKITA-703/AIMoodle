from selenium.common.exceptions import NoSuchElementException

from app.flows.test_flow import (
    _alternative_for_repeated_answer,
    _apply_explicit_review_feedback,
    _attach_review_scores,
    _build_review_feedback_hint,
    _get_all_answers_hint,
    _same_as_failed_answer,
    _latest_review_url,
    _open_review_page,
    _review_urls,
    _score_outcome,
    _find_keys_by_texts,
    _upsert_question_result,
)
from app.models import QuestionResult
from app.quiz_review import parse_question_reviews

from tests.test_quiz_review import REVIEW_HTML


def test_review_scores_are_attached_by_question_id():
    results = [
        QuestionResult(question_id="70474", question_text="Другой текст"),
        QuestionResult(question_id="70475", question_text="Выберите виды диаграмм"),
        QuestionResult(question_id="missing", question_text="Нет в обзоре"),
    ]

    _attach_review_scores(results, parse_question_reviews(REVIEW_HTML))

    assert results[0].outcome == "correct"
    assert results[0].score == 1.0
    assert results[1].outcome == "partial"
    assert results[1].score == 0.5
    assert results[2].outcome == "ungraded"


def test_score_outcomes():
    assert _score_outcome(1.0, 1.0) == "correct"
    assert _score_outcome(0.5, 1.0) == "partial"
    assert _score_outcome(0.0, 1.0) == "incorrect"
    assert _score_outcome(None, 1.0) == "ungraded"
    assert _score_outcome(None, None, "not_answered") == "not_answered"
    assert _score_outcome(0.0, 1.0, "partial") == "partial"


def test_question_result_is_not_duplicated_for_same_qid():
    results = [QuestionResult(question_id="42", selected_keys=["a"])]

    _upsert_question_result(results, QuestionResult(question_id="42", selected_keys=["b"]))

    assert len(results) == 1
    assert results[0].selected_keys == ["b"]


def test_partial_checkbox_feedback_survives_shuffled_option_letters():
    feedback = {
        "status": "partial",
        "score": 0.25,
        "max_score": 1.0,
        "selected_texts": ["b. Keras", "c. Неверный API"],
        "correct_texts": [],
        "incorrect_texts": [],
    }
    shuffled = {
        "a": "a. Неверный API",
        "b": "b. Другой ответ",
        "c": "c. Keras",
        "d": "d. Правильный API",
    }

    assert _same_as_failed_answer(["a", "c"], feedback, shuffled)
    assert not _same_as_failed_answer(["c", "d"], feedback, shuffled)
    hint = _build_review_feedback_hint([feedback], "checkbox")
    assert "0.25/1.0" in hint
    assert "добавь недостающие" in hint


def test_all_answers_option_adds_explicit_ai_check():
    hint = _get_all_answers_hint(
        {
            "a": "a. первый пункт",
            "b": "b. все перечисленное",
            "c": "c. третий пункт",
        },
        "checkbox",
    )

    assert "Вариант b" in hint
    assert "только этот вариант" in hint
    assert _get_all_answers_hint({"a": "a. все перечисленное"}, "radio") == ""


def test_explicit_review_feedback_adds_correct_and_removes_incorrect():
    feedback = {
        "correct_texts": ["b. Верный вариант"],
        "incorrect_texts": ["a. Ошибочный вариант"],
    }
    options = {
        "a": "a. Верный вариант",
        "b": "b. Ошибочный вариант",
        "c": "c. Новый вариант",
    }

    assert _apply_explicit_review_feedback(["b", "c"], feedback, options) == ["c", "a"]


def test_zero_score_for_all_specific_options_switches_to_all_answers():
    feedback = {
        "score": 0.0,
        "max_score": 1.0,
        "selected_texts": ["a. отображение", "b. стимул", "d. фокус"],
    }
    shuffled = {
        "a": "a. фокус",
        "b": "b. все перечисленное",
        "c": "c. отображение",
        "d": "d. стимул",
    }

    assert _alternative_for_repeated_answer(
        ["a", "c", "d"], feedback, shuffled
    ) == ["b"]


def test_partial_score_does_not_trigger_all_answers_heuristic():
    feedback = {
        "score": 0.25,
        "max_score": 1.0,
        "selected_texts": ["a. первый", "b. второй", "d. третий"],
    }
    options = {
        "a": "a. первый",
        "b": "b. второй",
        "c": "c. все ответы верны",
        "d": "d. третий",
    }

    assert _alternative_for_repeated_answer(["a", "b", "d"], feedback, options) == []


def test_review_link_is_opened_when_attempt_page_has_no_questions():
    class Link:
        def get_attribute(self, name):
            return "https://lms.example/mod/quiz/review.php?attempt=123" if name == "href" else ""

    class Driver:
        review_open = False
        current_url = "https://lms.example/mod/quiz/view.php?id=1"

        def find_elements(self, by, value):
            if value == ".que":
                return [object()] if self.review_open else []
            if "review.php" in value:
                return [Link()]
            return []

        def find_element(self, by, value):
            if value == ".que" and self.review_open:
                return object()
            raise NoSuchElementException()

        def get(self, url):
            self.current_url = url
            self.review_open = True

    driver = Driver()

    assert _open_review_page(driver) is True
    assert "review.php?attempt=123" in driver.current_url
    assert "showall=1" in driver.current_url


def test_saved_answer_is_matched_by_text_after_options_are_shuffled():
    current_options = {
        "a": "a. Неправильный новый вариант",
        "d": "d. Развязка по постоянному току",
    }

    keys = _find_keys_by_texts(["a. Развязка по постоянному току"], current_options)

    assert keys == ["d"]


def test_review_attempts_use_ids_instead_of_card_positions():
    class Link:
        def __init__(self, attempt_id):
            self.url = f"https://lms.example/mod/quiz/review.php?attempt={attempt_id}&cmid=651"

        def get_attribute(self, name):
            return self.url if name == "href" else ""

    class Driver:
        def find_elements(self, by, value):
            return [Link(3624572), Link(3624564), Link(3619032)]

    links = Driver().find_elements(None, None)

    assert [url.split("attempt=")[1].split("&")[0] for url in _review_urls(Driver())] == [
        "3619032",
        "3624564",
        "3624572",
    ]
    assert "attempt=3624572" in _latest_review_url(links)
