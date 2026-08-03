from app import quiz_memory

from tests.test_quiz_review import REVIEW_HTML


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

