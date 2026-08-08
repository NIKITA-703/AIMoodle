from app import stats
import json
import sqlite3

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


def test_course_completion_cache_is_persistent_and_clearable(tmp_path, monkeypatch):
    monkeypatch.setattr(stats, "DATABASE_FILE", tmp_path / "bot.db")
    monkeypatch.setattr(stats, "STATS_FILE", tmp_path / "missing.json")
    course_url = "https://lms/course/view.php?id=74"

    stats.mark_course_tests_complete(course_url, "Эконометрика")

    assert stats.get_cached_completed_course_urls(30) == {course_url}

    stats.clear_course_test_status(course_url)

    assert stats.get_cached_completed_course_urls(30) == set()


def test_question_analysis_groups_existing_results(tmp_path, monkeypatch):
    monkeypatch.setattr(stats, "DATABASE_FILE", tmp_path / "bot.db")
    monkeypatch.setattr(stats, "STATS_FILE", tmp_path / "missing.json")

    run_id = stats.start_run()
    result = QuizResult(
        submitted=True,
        question_results=[
            QuestionResult(
                question_type="radio",
                question_text="Вопрос 1",
                source="lecture",
                context_mode="selected",
                score=1.0,
                max_score=1.0,
                outcome="correct",
                response_time_sec=2.0,
            ),
            QuestionResult(
                question_type="checkbox",
                question_text="Вопрос 2",
                source="general_knowledge",
                context_mode="none",
                score=0.5,
                max_score=1.0,
                outcome="partial",
                response_time_sec=4.0,
            ),
            QuestionResult(
                question_type="text",
                question_text="Вопрос без обзора",
                source="memory",
                outcome="ungraded",
            ),
        ],
    )
    stats.record_attempt(run_id, "Курс", "Тест", result, 10)

    analysis = stats.get_question_analysis()

    assert analysis["total"] == 3
    assert analysis["graded"] == 2
    assert analysis["ungraded"] == 1
    assert analysis["by_source"][0]["label"] in {"general_knowledge", "lecture"}
    lecture = next(row for row in analysis["by_source"] if row["label"] == "lecture")
    checkbox = next(row for row in analysis["by_type"] if row["label"] == "checkbox")
    assert lecture["average_score_percent"] == 100.0
    assert checkbox["partial"] == 1
    assert checkbox["average_score_percent"] == 50.0


def test_run_version_and_lecture_context_metadata_are_linked(tmp_path, monkeypatch):
    monkeypatch.setattr(stats, "DATABASE_FILE", tmp_path / "bot.db")
    monkeypatch.setattr(stats, "STATS_FILE", tmp_path / "missing.json")
    monkeypatch.setattr(stats, "_git_state", lambda: ("abc123", False))

    run_id = stats.start_run(
        model_name="qwen/qwen3-14b",
        settings={"parallel_workers": 2, "tests_limit": 5},
    )
    attempt_id = stats.record_attempt(
        run_id,
        "Курс",
        "Тест",
        QuizResult(submitted=True),
        duration_sec=10,
        lecture_text="### Лекция 1\nТекст лекции",
    )

    with stats._connect() as connection:
        run = connection.execute(
            """
            SELECT r.*, v.bot_version, v.git_commit, v.memory_version, v.context_version
            FROM runs r JOIN bot_versions v ON v.id = r.bot_version_id
            WHERE r.id = ?
            """,
            (run_id,),
        ).fetchone()
        lecture = connection.execute(
            """
            SELECT l.*
            FROM lecture_contexts l
            JOIN attempt_lecture_contexts al ON al.lecture_context_id = l.id
            WHERE al.attempt_id = ?
            """,
            (attempt_id,),
        ).fetchone()
        lecture_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(lecture_contexts)")
        }
        schema_version = connection.execute("PRAGMA user_version").fetchone()[0]

    assert run["bot_version"] == stats.BOT_VERSION
    assert run["git_commit"] == "abc123"
    assert run["memory_version"] == stats.MEMORY_VERSION
    assert run["context_version"] == stats.CONTEXT_VERSION
    assert run["model_name"] == "qwen/qwen3-14b"
    assert json.loads(run["settings_json"])["parallel_workers"] == 2
    assert lecture["character_count"] == len("### Лекция 1\nТекст лекции")
    assert lecture["material_count"] == 1
    assert len(lecture["content_sha256"]) == 64
    assert "content" not in lecture_columns
    assert "text" not in lecture_columns
    assert schema_version == stats.DATABASE_SCHEMA_VERSION


def test_existing_runs_are_migrated_to_legacy_version(tmp_path, monkeypatch):
    database = tmp_path / "bot.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                uptime_sec REAL NOT NULL DEFAULT 0,
                errors_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        connection.execute("INSERT INTO runs(started_at) VALUES ('2026-01-01T00:00:00')")

    monkeypatch.setattr(stats, "DATABASE_FILE", database)
    monkeypatch.setattr(stats, "STATS_FILE", tmp_path / "missing.json")
    stats.initialize_database()

    with stats._connect() as connection:
        migrated = connection.execute(
            """
            SELECT r.model_name, r.settings_json, v.bot_version,
                   v.memory_version, v.context_version
            FROM runs r JOIN bot_versions v ON v.id = r.bot_version_id
            WHERE r.id = 1
            """
        ).fetchone()

    assert migrated["bot_version"] == "legacy"
    assert migrated["memory_version"] == "unknown"
    assert migrated["context_version"] == "unknown"
    assert migrated["model_name"] == ""
    assert migrated["settings_json"] == "{}"
