import json
import sqlite3
from datetime import datetime

from app.config import DATABASE_FILE, STATS_FILE


def format_duration(seconds):
    seconds = int(seconds or 0)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}ч {m}м {s}с"


def initialize_database():
    with _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                uptime_sec REAL NOT NULL DEFAULT 0,
                errors_count INTEGER NOT NULL DEFAULT 0
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
            """
        )


def start_run():
    initialize_database()
    with _connect() as connection:
        cursor = connection.execute(
            "INSERT INTO runs(started_at) VALUES (?)",
            (_now(),),
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


def record_attempt(run_id, course_name, test_name, result, duration_sec, started_at=None):
    source_counts = result.source_counts or {}
    with _connect() as connection:
        connection.execute(
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
        "legacy_tests": int(legacy.get("total_tests", 0) or 0),
        "legacy_uptime_sec": float(legacy.get("total_uptime_sec", 0) or 0),
    }


def _connect():
    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    return connection


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
