from app import stats
import json

from app.models import QuestionResult, QuizResult


def test_sqlite_stats_separate_attempts_and_passed_tests(tmp_path, monkeypatch):
    monkeypatch.setattr(stats, "DATABASE_FILE", tmp_path / "bot.db")
    monkeypatch.setattr(stats, "STATS_FILE", tmp_path / "missing.json")

    run_id = stats.start_run()
    failed = QuizResult(
        submitted=True,
        passed=False,
        grade_percent=47.5,
        pass_grade=60.0,
        question_results=[
            QuestionResult(
                question_id="70474",
                question_number="1",
                question_type="radio",
                question_text="Верно ли утверждение?",
                options={"a": "Верно", "b": "Неверно"},
                selected_keys=["b"],
                selected_texts=["Неверно"],
                correct_keys=["a"],
                incorrect_keys=["b"],
                source="lecture",
                evidence="Фрагмент текста лекции",
                context_mode="full",
                response_time_sec=1.25,
                score=0.0,
                max_score=1.0,
                outcome="incorrect",
            )
        ],
    )
    passed = QuizResult(submitted=True, passed=True, grade_percent=75.0, pass_grade=60.0)

    stats.record_attempt(run_id, "Курс", "Тест", failed, 10)
    stats.record_attempt(run_id, "Курс", "Тест", passed, 12)
    stats.finish_run(run_id, 30)
    summary = stats.get_global_stats()

    assert summary["total_attempts"] == 2
    assert summary["passed_tests"] == 1
    assert summary["failed_attempts"] == 1
    assert summary["average_grade"] == 61.25
    assert summary["total_test_time_sec"] == 22
    assert summary["total_questions"] == 1
    assert summary["incorrect_questions"] == 1

    with stats._connect() as connection:
        question = connection.execute("SELECT * FROM question_results").fetchone()

    assert question["question_id"] == "70474"
    assert json.loads(question["selected_keys_json"]) == ["b"]
    assert question["source"] == "lecture"
    assert question["evidence"] == "Фрагмент текста лекции"
    assert json.loads(question["correct_keys_json"]) == ["a"]
    assert json.loads(question["incorrect_keys_json"]) == ["b"]
