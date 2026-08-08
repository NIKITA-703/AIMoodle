from concurrent.futures import ThreadPoolExecutor

from app import quiz_memory, runner, stats
from app.models import QuizResult
from tests.test_quiz_review import EXPLICIT_FEEDBACK_HTML


class DiscoveryDriver:
    current_url = ""

    def get(self, url):
        self.current_url = url


def test_coordinator_assigns_one_test_from_each_distinct_course(monkeypatch):
    driver = DiscoveryDriver()
    courses = [
        ("https://lms/course/view.php?id=1", "Без тестов", "Проходите сейчас"),
        ("https://lms/course/view.php?id=2", "Курс 2", "Проходите сейчас"),
        ("https://lms/course/view.php?id=3", "Курс 3", "Пересдача"),
    ]
    tests = {
        courses[0][0]: (None, None, None),
        courses[1][0]: ("Тест 2", "https://lms/mod/quiz/view.php?id=20", "Тема 2"),
        courses[2][0]: ("Тест 3", "https://lms/mod/quiz/view.php?id=30", "Тема 3"),
    }

    monkeypatch.setattr(runner, "get_active_course_links", lambda _driver: courses)
    monkeypatch.setattr(
        runner,
        "find_current_test_info",
        lambda current_driver: tests[current_driver.current_url],
    )

    assignments = runner._discover_course_assignments(driver, limit=2)

    assert [item.course_name for item in assignments] == ["Курс 2", "Курс 3"]
    assert len({item.course_url for item in assignments}) == 2


def test_parallel_runner_starts_each_assignment_once(monkeypatch):
    assignments = [
        runner.CourseAssignment("course-1", "Курс 1", "Тест 1", "quiz-1"),
        runner.CourseAssignment("course-2", "Курс 2", "Тест 2", "quiz-2"),
    ]
    calls = []

    def fake_worker(worker_id, assignment, run_id, budget):
        calls.append((worker_id, assignment.course_url, run_id))
        assert budget.limit == 2
        return runner.WorkerOutcome(worker_id, assignment.course_name, submitted=1, passed=1)

    monkeypatch.setattr(runner, "_course_worker", fake_worker)
    outcomes = runner._run_parallel_workers(assignments, run_id=99)

    assert sorted(calls) == [(1, "course-1", 99), (2, "course-2", 99)]
    assert sum(item.submitted for item in outcomes) == 2


def test_worker_retries_failed_test_before_moving_on(monkeypatch):
    assignment = runner.CourseAssignment("course-1", "Курс 1", "Тест 1", "quiz-1")
    results = iter(
        [
            QuizResult(
                submitted=True,
                passed=False,
                grade_percent=50,
                pass_grade=60,
                remaining_attempts=2,
                new_confirmed_answers=3,
            ),
            QuizResult(
                submitted=True,
                passed=True,
                grade_percent=80,
                pass_grade=60,
                remaining_attempts=1,
            ),
        ]
    )
    calls = []

    class WorkerDriver:
        def quit(self):
            pass

    monkeypatch.setattr(runner, "_create_driver", lambda: WorkerDriver())
    monkeypatch.setattr(runner, "_open_authenticated_home", lambda _driver: True)

    def fake_execute(_driver, current, _run_id, _prefix, lecture_text=None):
        calls.append(current.test_url)
        return next(results), "лекция"

    monkeypatch.setattr(runner, "_execute_assigned_attempt", fake_execute)
    monkeypatch.setattr(runner, "_find_next_course_assignment", lambda *_args: None)

    outcome = runner._course_worker(1, assignment, run_id=5, budget=runner.AttemptBudget(3))

    assert calls == ["quiz-1", "quiz-1"]
    assert outcome.submitted == 2
    assert outcome.passed == 1


def test_attempt_budget_never_exceeds_global_limit():
    budget = runner.AttemptBudget(5)

    def reserve_and_submit(_):
        if not budget.reserve():
            return False
        budget.complete(True)
        return True

    with ThreadPoolExecutor(max_workers=4) as executor:
        accepted = list(executor.map(reserve_and_submit, range(20)))

    assert sum(accepted) == 5
    assert budget.submitted == 5


def test_quiz_memory_keeps_concurrent_review_updates(tmp_path, monkeypatch):
    memory_file = tmp_path / "quiz_memory.json"
    monkeypatch.setattr(quiz_memory, "QUIZ_MEMORY_FILE", memory_file)

    class ReviewDriver:
        page_source = EXPLICIT_FEEDBACK_HTML

        def __init__(self, attempt_id):
            self.current_url = (
                "https://lms/mod/quiz/review.php?attempt="
                f"{attempt_id}&cmid=651"
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                quiz_memory.record_review_results,
                ReviewDriver(attempt_id),
                "Курс",
                "Тест",
                "1",
                "651",
            )
            for attempt_id in (1001, 1002)
        ]
        for future in futures:
            future.result()

    memory = quiz_memory.load_quiz_memory()
    scope = memory["scopes"]["course:1|quiz:651"]
    assert sorted(scope["captured_attempt_ids"]) == ["1001", "1002"]
    assert all(len(question["attempts"]) == 2 for question in scope["questions"].values())


def test_sqlite_accepts_concurrent_attempt_records(tmp_path, monkeypatch):
    monkeypatch.setattr(stats, "DATABASE_FILE", tmp_path / "bot.db")
    monkeypatch.setattr(stats, "STATS_FILE", tmp_path / "missing.json")
    run_id = stats.start_run()

    def write_attempt(number):
        stats.record_attempt(
            run_id,
            f"Курс {number}",
            f"Тест {number}",
            QuizResult(submitted=True, passed=True, grade_percent=100),
            duration_sec=1,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(write_attempt, (1, 2)))

    assert stats.get_global_stats()["total_attempts"] == 2
