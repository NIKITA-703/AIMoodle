from app import quiz_memory

from tests.test_quiz_review import EXPLICIT_FEEDBACK_HTML, REVIEW_HTML


class FakeDriver:
    page_source = REVIEW_HTML


def test_memory_uses_qid_and_does_not_confirm_partial_checkbox(tmp_path, monkeypatch):
    memory_file = tmp_path / "quiz_memory.json"
    monkeypatch.setattr(quiz_memory, "QUIZ_MEMORY_FILE", memory_file)

    result = quiz_memory.record_review_results(
        FakeDriver(),
        "Курс",
        "Тест",
        course_id="74",
        quiz_id="6143",
    )

    radio_answer = quiz_memory.get_confirmed_answer(
        "Курс",
        "Тест",
        "Формулировка может измениться",
        course_id="74",
        quiz_id="6143",
        question_id="70474",
    )
    partial_checkbox = quiz_memory.get_confirmed_answer(
        "Курс",
        "Тест",
        "Выберите виды диаграмм",
        course_id="74",
        quiz_id="6143",
        question_id="70475",
    )
    binary_inverse = quiz_memory.get_confirmed_answer(
        "Курс",
        "Тест",
        "Это правильно?",
        course_id="74",
        quiz_id="6143",
        question_id="70476",
    )

    assert result["saved_count"] == 3
    assert radio_answer["keys"] == ["b"]
    assert partial_checkbox is None
    assert binary_inverse["keys"] == ["b"]


def test_memory_uses_explicit_review_feedback_for_checkbox(tmp_path, monkeypatch):
    memory_file = tmp_path / "quiz_memory.json"
    monkeypatch.setattr(quiz_memory, "QUIZ_MEMORY_FILE", memory_file)

    class FeedbackDriver:
        page_source = EXPLICIT_FEEDBACK_HTML.replace(
            "qnbutton partiallycorrect", "qnbutton correct"
        ).replace("0,75 из 1,00", "1,00 из 1,00")

    quiz_memory.record_review_results(
        FeedbackDriver(),
        "Курс",
        "Тест",
        course_id="74",
        quiz_id="6143",
    )
    answer = quiz_memory.get_confirmed_answer(
        "Курс",
        "Тест",
        "Какие каналы существуют?",
        course_id="74",
        quiz_id="6143",
        question_id="90001",
    )

    assert answer["keys"] == ["b", "c"]
    assert answer["source"] == "review_feedback"


def test_partial_checkbox_feedback_is_not_confirmed_as_complete(tmp_path, monkeypatch):
    memory_file = tmp_path / "quiz_memory.json"
    monkeypatch.setattr(quiz_memory, "QUIZ_MEMORY_FILE", memory_file)

    class FeedbackDriver:
        page_source = EXPLICIT_FEEDBACK_HTML

    quiz_memory.record_review_results(
        FeedbackDriver(), "Курс", "Тест", course_id="74", quiz_id="6143"
    )
    answer = quiz_memory.get_confirmed_answer(
        "Курс",
        "Тест",
        "Какие каналы существуют?",
        course_id="74",
        quiz_id="6143",
        question_id="90001",
    )

    assert answer is None


def test_same_review_attempt_is_not_recorded_twice(tmp_path, monkeypatch):
    memory_file = tmp_path / "quiz_memory.json"
    monkeypatch.setattr(quiz_memory, "QUIZ_MEMORY_FILE", memory_file)

    class FeedbackDriver:
        page_source = EXPLICIT_FEEDBACK_HTML
        current_url = "https://lms.example/mod/quiz/review.php?attempt=3619032&cmid=651"

    first = quiz_memory.record_review_results(FeedbackDriver(), "Курс", "Тест", quiz_id="651")
    second = quiz_memory.record_review_results(FeedbackDriver(), "Курс", "Тест", quiz_id="651")

    assert first["saved_count"] == 2
    assert second["already_captured"] is True
    data = quiz_memory.load_quiz_memory()
    scope = data["scopes"]["course:unknown|quiz:651"]
    assert scope["captured_attempt_ids"] == ["3619032"]
