from app import stats
from app.models import QuizResult


def test_sqlite_stats_separate_attempts_and_passed_tests(tmp_path, monkeypatch):
    monkeypatch.setattr(stats, "DATABASE_FILE", tmp_path / "bot.db")
    monkeypatch.setattr(stats, "STATS_FILE", tmp_path / "missing.json")

    run_id = stats.start_run()
    failed = QuizResult(submitted=True, passed=False, grade_percent=47.5, pass_grade=60.0)
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

