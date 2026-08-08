import json
import hashlib
import sqlite3
import subprocess
from datetime import datetime, timedelta

from app.config import (
    BASE_DIR,
    BOT_VERSION,
    CONTEXT_VERSION,
    DATABASE_FILE,
    MEMORY_VERSION,
    STATS_FILE,
)

DATABASE_SCHEMA_VERSION = 3


def format_duration(seconds):
    seconds = int(seconds or 0)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}ч {m}м {s}с"


def initialize_database():
    with _connect() as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS bot_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_version TEXT NOT NULL,
                git_commit TEXT NOT NULL DEFAULT 'unknown',
                git_dirty INTEGER NOT NULL DEFAULT 0,
                memory_version TEXT NOT NULL,
                context_version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(bot_version, git_commit, git_dirty, memory_version, context_version)
            );

            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_version_id INTEGER,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                uptime_sec REAL NOT NULL DEFAULT 0,
                errors_count INTEGER NOT NULL DEFAULT 0,
                model_name TEXT NOT NULL DEFAULT '',
                settings_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY (bot_version_id) REFERENCES bot_versions(id)
            );

            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                course_name TEXT NOT NULL,
                test_name TEXT NOT NULL,
                attempt_number INTEGER,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                duration_sec REAL NOT NULL DEFAULT 0,
                score REAL,
                max_score REAL,
                grade_percent REAL,
                pass_grade REAL,
                submitted INTEGER NOT NULL DEFAULT 0,
                passed INTEGER NOT NULL DEFAULT 0,
                remaining_attempts INTEGER,
                lecture_answers INTEGER NOT NULL DEFAULT 0,
                memory_answers INTEGER NOT NULL DEFAULT 0,
                general_answers INTEGER NOT NULL DEFAULT 0,
                new_confirmed_answers INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (run_id) REFERENCES runs(id)
            );

            CREATE TABLE IF NOT EXISTS question_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attempt_id INTEGER NOT NULL,
                question_id TEXT NOT NULL DEFAULT '',
                question_number TEXT NOT NULL DEFAULT '',
                question_type TEXT NOT NULL DEFAULT 'unknown',
                question_text TEXT NOT NULL,
                options_json TEXT NOT NULL DEFAULT '{}',
                selected_keys_json TEXT NOT NULL DEFAULT '[]',
                selected_texts_json TEXT NOT NULL DEFAULT '[]',
                correct_keys_json TEXT NOT NULL DEFAULT '[]',
                incorrect_keys_json TEXT NOT NULL DEFAULT '[]',
                text_answer TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'general_knowledge',
                evidence TEXT NOT NULL DEFAULT '',
                context_mode TEXT NOT NULL DEFAULT 'none',
                response_time_sec REAL NOT NULL DEFAULT 0,
                score REAL,
                max_score REAL,
                outcome TEXT NOT NULL DEFAULT 'ungraded',
                created_at TEXT NOT NULL,
                FOREIGN KEY (attempt_id) REFERENCES attempts(id)
            );

            CREATE INDEX IF NOT EXISTS idx_question_results_attempt
                ON question_results(attempt_id);
            CREATE INDEX IF NOT EXISTS idx_question_results_qid
                ON question_results(question_id);
            CREATE INDEX IF NOT EXISTS idx_question_results_outcome
                ON question_results(outcome);

            CREATE TABLE IF NOT EXISTS lecture_contexts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_name TEXT NOT NULL,
                content_sha256 TEXT NOT NULL,
                character_count INTEGER NOT NULL,
                material_count INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                UNIQUE(course_name, content_sha256)
            );

            CREATE TABLE IF NOT EXISTS attempt_lecture_contexts (
                attempt_id INTEGER NOT NULL,
                lecture_context_id INTEGER NOT NULL,
                PRIMARY KEY (attempt_id, lecture_context_id),
                FOREIGN KEY (attempt_id) REFERENCES attempts(id),
                FOREIGN KEY (lecture_context_id) REFERENCES lecture_contexts(id)
            );

            CREATE INDEX IF NOT EXISTS idx_lecture_contexts_hash
                ON lecture_contexts(content_sha256);

            CREATE TABLE IF NOT EXISTS course_test_status (
                course_url TEXT PRIMARY KEY,
                course_name TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                checked_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_course_test_status_checked
                ON course_test_status(status, checked_at);
            """
        )
        _ensure_column(connection, "runs", "bot_version_id", "INTEGER")
        _ensure_column(connection, "runs", "model_name", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(connection, "runs", "settings_json", "TEXT NOT NULL DEFAULT '{}'")
        _ensure_column(connection, "question_results", "correct_keys_json", "TEXT NOT NULL DEFAULT '[]'")
        _ensure_column(connection, "question_results", "incorrect_keys_json", "TEXT NOT NULL DEFAULT '[]'")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_bot_version ON runs(bot_version_id)"
        )
        legacy_version_id = _get_or_create_bot_version(
            connection,
            bot_version="legacy",
            git_commit="unknown",
            git_dirty=False,
            memory_version="unknown",
            context_version="unknown",
        )
        connection.execute(
            "UPDATE runs SET bot_version_id = ? WHERE bot_version_id IS NULL",
            (legacy_version_id,),
        )
        connection.execute(f"PRAGMA user_version = {DATABASE_SCHEMA_VERSION}")


def start_run(model_name="", settings=None):
    initialize_database()
    with _connect() as connection:
        git_commit, git_dirty = _git_state()
        version_id = _get_or_create_bot_version(
            connection,
            bot_version=BOT_VERSION,
            git_commit=git_commit,
            git_dirty=git_dirty,
            memory_version=MEMORY_VERSION,
            context_version=CONTEXT_VERSION,
        )
        cursor = connection.execute(
            """
            INSERT INTO runs(bot_version_id, started_at, model_name, settings_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                version_id,
                _now(),
                model_name or "",
                json.dumps(settings or {}, ensure_ascii=False, sort_keys=True),
            ),
        )
        return cursor.lastrowid


def finish_run(run_id, uptime_sec, errors_count=0):
    if not run_id:
        return
    with _connect() as connection:
        connection.execute(
            """
            UPDATE runs
            SET finished_at = ?, uptime_sec = ?, errors_count = ?
            WHERE id = ?
            """,
            (_now(), float(uptime_sec or 0), int(errors_count or 0), run_id),
        )


def mark_course_tests_complete(course_url, course_name, reason="no_available_tests"):
    if not course_url:
        return
    initialize_database()
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO course_test_status(
                course_url, course_name, status, reason, checked_at
            ) VALUES (?, ?, 'tests_complete', ?, ?)
            ON CONFLICT(course_url) DO UPDATE SET
                course_name = excluded.course_name,
                status = excluded.status,
                reason = excluded.reason,
                checked_at = excluded.checked_at
            """,
            (course_url, course_name or "", reason or "", _now()),
        )


def clear_course_test_status(course_url):
    if not course_url:
        return
    initialize_database()
    with _connect() as connection:
        connection.execute(
            "DELETE FROM course_test_status WHERE course_url = ?",
            (course_url,),
        )


def get_cached_completed_course_urls(max_age_days=30):
    initialize_database()
    cutoff = datetime.now() - timedelta(days=max(1, int(max_age_days or 1)))
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT course_url, checked_at
            FROM course_test_status
            WHERE status = 'tests_complete'
            """
        ).fetchall()

    result = set()
    for row in rows:
        try:
            checked_at = datetime.fromisoformat(row["checked_at"])
        except (TypeError, ValueError):
            continue
        if checked_at >= cutoff:
            result.add(row["course_url"])
    return result


def record_attempt(
    run_id,
    course_name,
    test_name,
    result,
    duration_sec,
    started_at=None,
    lecture_text="",
):
    source_counts = result.source_counts or {}
    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO attempts(
                run_id, course_name, test_name, attempt_number,
                started_at, finished_at, duration_sec,
                score, max_score, grade_percent, pass_grade,
                submitted, passed, remaining_attempts,
                lecture_answers, memory_answers, general_answers,
                new_confirmed_answers, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                course_name,
                test_name,
                result.attempt_number,
                started_at or _now(),
                _now(),
                float(duration_sec or 0),
                result.score,
                result.max_score,
                result.grade_percent,
                result.pass_grade,
                int(bool(result.submitted)),
                int(bool(result.passed)),
                result.remaining_attempts,
                int(source_counts.get("lecture", 0)),
                int(source_counts.get("memory", 0)),
                int(source_counts.get("general_knowledge", 0)),
                int(result.new_confirmed_answers or 0),
                result.error or "",
            ),
        )
        attempt_id = cursor.lastrowid
        if lecture_text and lecture_text.strip():
            _record_lecture_context(connection, attempt_id, course_name, lecture_text)
        for question in result.question_results or []:
            connection.execute(
                """
                INSERT INTO question_results(
                    attempt_id, question_id, question_number, question_type,
                    question_text, options_json, selected_keys_json,
                    selected_texts_json, correct_keys_json, incorrect_keys_json,
                    text_answer, source, evidence,
                    context_mode, response_time_sec, score, max_score,
                    outcome, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    question.question_id or "",
                    question.question_number or "",
                    question.question_type or "unknown",
                    question.question_text or "",
                    json.dumps(question.options or {}, ensure_ascii=False),
                    json.dumps(question.selected_keys or [], ensure_ascii=False),
                    json.dumps(question.selected_texts or [], ensure_ascii=False),
                    json.dumps(question.correct_keys or [], ensure_ascii=False),
                    json.dumps(question.incorrect_keys or [], ensure_ascii=False),
                    question.text_answer or "",
                    question.source or "general_knowledge",
                    question.evidence or "",
                    question.context_mode or "none",
                    float(question.response_time_sec or 0),
                    question.score,
                    question.max_score,
                    question.outcome or "ungraded",
                    _now(),
                ),
            )
        return attempt_id


def get_global_stats():
    initialize_database()
    with _connect() as connection:
        attempts = connection.execute(
            """
            SELECT
                COUNT(*) AS total_attempts,
                COALESCE(SUM(passed), 0) AS passed_tests,
                COALESCE(SUM(CASE WHEN submitted = 1 AND passed = 0 THEN 1 ELSE 0 END), 0) AS failed_attempts,
                COALESCE(SUM(CASE WHEN submitted = 0 THEN 1 ELSE 0 END), 0) AS interrupted_attempts,
                COALESCE(SUM(duration_sec), 0) AS total_test_time_sec,
                AVG(CASE WHEN submitted = 1 THEN grade_percent END) AS average_grade,
                COALESCE(SUM(lecture_answers), 0) AS lecture_answers,
                COALESCE(SUM(memory_answers), 0) AS memory_answers,
                COALESCE(SUM(general_answers), 0) AS general_answers
            FROM attempts
            """
        ).fetchone()
        runs = connection.execute(
            "SELECT COALESCE(SUM(uptime_sec), 0) AS total_uptime_sec FROM runs"
        ).fetchone()
        questions = connection.execute(
            """
            SELECT
                COUNT(*) AS total_questions,
                COALESCE(SUM(CASE WHEN outcome = 'correct' THEN 1 ELSE 0 END), 0) AS correct_questions,
                COALESCE(SUM(CASE WHEN outcome = 'partial' THEN 1 ELSE 0 END), 0) AS partial_questions,
                COALESCE(SUM(CASE WHEN outcome = 'incorrect' THEN 1 ELSE 0 END), 0) AS incorrect_questions,
                COALESCE(SUM(CASE WHEN outcome = 'not_answered' THEN 1 ELSE 0 END), 0) AS unanswered_questions,
                COALESCE(SUM(CASE WHEN outcome = 'ungraded' THEN 1 ELSE 0 END), 0) AS ungraded_questions
            FROM question_results
            """
        ).fetchone()

    legacy = _load_legacy_stats()
    return {
        "total_attempts": attempts["total_attempts"],
        "passed_tests": attempts["passed_tests"],
        "failed_attempts": attempts["failed_attempts"],
        "interrupted_attempts": attempts["interrupted_attempts"],
        "total_test_time_sec": attempts["total_test_time_sec"],
        "total_uptime_sec": runs["total_uptime_sec"],
        "average_grade": attempts["average_grade"],
        "lecture_answers": attempts["lecture_answers"],
        "memory_answers": attempts["memory_answers"],
        "general_answers": attempts["general_answers"],
        "total_questions": questions["total_questions"],
        "correct_questions": questions["correct_questions"],
        "partial_questions": questions["partial_questions"],
        "incorrect_questions": questions["incorrect_questions"],
        "unanswered_questions": questions["unanswered_questions"],
        "ungraded_questions": questions["ungraded_questions"],
        "legacy_tests": int(legacy.get("total_tests", 0) or 0),
        "legacy_uptime_sec": float(legacy.get("total_uptime_sec", 0) or 0),
    }


def get_question_analysis():
    """Build aggregated quality metrics from already recorded question results."""
    initialize_database()
    with _connect() as connection:
        coverage = connection.execute(
            """
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(CASE WHEN outcome != 'ungraded' THEN 1 ELSE 0 END), 0) AS graded,
                COALESCE(SUM(CASE WHEN outcome = 'ungraded' THEN 1 ELSE 0 END), 0) AS ungraded
            FROM question_results
            """
        ).fetchone()
        by_source = _quality_breakdown(connection, "source")
        by_type = _quality_breakdown(connection, "question_type")
        by_context = _quality_breakdown(connection, "context_mode")
        by_version = _quality_by_version(connection)

    return {
        "total": coverage["total"],
        "graded": coverage["graded"],
        "ungraded": coverage["ungraded"],
        "by_source": by_source,
        "by_type": by_type,
        "by_context": by_context,
        "by_version": by_version,
    }


def print_question_analysis():
    analysis = get_question_analysis()
    print("\nАнализ качества ответов")
    print(f"Всего записей вопросов: {analysis['total']}")
    print(f"С оценкой Moodle: {analysis['graded']}")
    print(f"Без оценки: {analysis['ungraded']}")

    if not analysis["graded"]:
        print("Недостаточно оценённых вопросов для анализа.")
        return

    _print_quality_table("По источнику ответа", analysis["by_source"])
    _print_quality_table("По типу вопроса", analysis["by_type"])
    _print_quality_table("По режиму контекста", analysis["by_context"])
    _print_quality_table("По версии бота", analysis["by_version"])


def _quality_breakdown(connection, column):
    allowed_columns = {"source", "question_type", "context_mode"}
    if column not in allowed_columns:
        raise ValueError(f"Unsupported analysis column: {column}")

    rows = connection.execute(
        f"""
        SELECT
            {column} AS label,
            COUNT(*) AS total,
            COALESCE(SUM(CASE WHEN outcome = 'correct' THEN 1 ELSE 0 END), 0) AS correct,
            COALESCE(SUM(CASE WHEN outcome = 'partial' THEN 1 ELSE 0 END), 0) AS partial,
            COALESCE(SUM(CASE WHEN outcome = 'incorrect' THEN 1 ELSE 0 END), 0) AS incorrect,
            COALESCE(SUM(CASE WHEN outcome = 'not_answered' THEN 1 ELSE 0 END), 0) AS unanswered,
            AVG(CASE WHEN max_score > 0 THEN score * 100.0 / max_score END) AS average_score_percent,
            AVG(response_time_sec) AS average_response_time_sec
        FROM question_results
        WHERE outcome != 'ungraded'
        GROUP BY {column}
        ORDER BY total DESC, label
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _quality_by_version(connection):
    rows = connection.execute(
        """
        SELECT
            v.bot_version || ' | mem=' || v.memory_version || ' | ctx=' || v.context_version AS label,
            COUNT(*) AS total,
            COALESCE(SUM(CASE WHEN q.outcome = 'correct' THEN 1 ELSE 0 END), 0) AS correct,
            COALESCE(SUM(CASE WHEN q.outcome = 'partial' THEN 1 ELSE 0 END), 0) AS partial,
            COALESCE(SUM(CASE WHEN q.outcome = 'incorrect' THEN 1 ELSE 0 END), 0) AS incorrect,
            COALESCE(SUM(CASE WHEN q.outcome = 'not_answered' THEN 1 ELSE 0 END), 0) AS unanswered,
            AVG(CASE WHEN q.max_score > 0 THEN q.score * 100.0 / q.max_score END) AS average_score_percent,
            AVG(q.response_time_sec) AS average_response_time_sec
        FROM question_results q
        JOIN attempts a ON a.id = q.attempt_id
        JOIN runs r ON r.id = a.run_id
        JOIN bot_versions v ON v.id = r.bot_version_id
        WHERE q.outcome != 'ungraded'
        GROUP BY v.id
        ORDER BY total DESC, label
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _print_quality_table(title, rows):
    label_width = min(60, max([24, *(len(row["label"] or "unknown") for row in rows)]))
    print(f"\n{title}:")
    print(f"{'Категория':<{label_width}} {'Всего':>6} {'Верно':>6} {'Част.':>6} {'Ошиб.':>6} {'Нет':>5} {'Точность':>9} {'Время':>8}")
    for row in rows:
        average_score = row["average_score_percent"]
        accuracy = f"{average_score:.1f}%" if average_score is not None else "-"
        response_time = row["average_response_time_sec"]
        time_text = f"{response_time:.1f}с" if response_time is not None else "-"
        print(
            f"{(row['label'] or 'unknown'):<{label_width}} "
            f"{row['total']:>6} {row['correct']:>6} {row['partial']:>6} "
            f"{row['incorrect']:>6} {row['unanswered']:>5} {accuracy:>9} {time_text:>8}"
        )


def _connect():
    connection = sqlite3.connect(DATABASE_FILE, timeout=30)
    connection.execute("PRAGMA busy_timeout=30000")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.row_factory = sqlite3.Row
    return connection


def _get_or_create_bot_version(
    connection,
    bot_version,
    git_commit,
    git_dirty,
    memory_version,
    context_version,
):
    values = (
        bot_version,
        git_commit or "unknown",
        int(bool(git_dirty)),
        memory_version,
        context_version,
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO bot_versions(
            bot_version, git_commit, git_dirty, memory_version,
            context_version, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (*values, _now()),
    )
    row = connection.execute(
        """
        SELECT id FROM bot_versions
        WHERE bot_version = ? AND git_commit = ? AND git_dirty = ?
          AND memory_version = ? AND context_version = ?
        """,
        values,
    ).fetchone()
    return row["id"]


def _record_lecture_context(connection, attempt_id, course_name, lecture_text):
    normalized = lecture_text.strip()
    content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    material_count = max(1, sum(1 for line in normalized.splitlines() if line.startswith("### ")))
    connection.execute(
        """
        INSERT OR IGNORE INTO lecture_contexts(
            course_name, content_sha256, character_count,
            material_count, created_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (course_name, content_hash, len(normalized), material_count, _now()),
    )
    context_id = connection.execute(
        """
        SELECT id FROM lecture_contexts
        WHERE course_name = ? AND content_sha256 = ?
        """,
        (course_name, content_hash),
    ).fetchone()["id"]
    connection.execute(
        """
        INSERT OR IGNORE INTO attempt_lecture_contexts(attempt_id, lecture_context_id)
        VALUES (?, ?)
        """,
        (attempt_id, context_id),
    )


def _git_state():
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--"],
            cwd=BASE_DIR,
            capture_output=True,
            timeout=3,
            check=False,
        ).returncode != 0
        return commit or "unknown", dirty
    except Exception:
        return "unknown", False


def _ensure_column(connection, table_name, column_name, declaration):
    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {declaration}"
        )


def _load_legacy_stats():
    if not STATS_FILE.exists():
        return {}
    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _now():
    return datetime.now().isoformat(timespec="seconds")
