import json
import os
from datetime import datetime

from app.config import STATS_FILE


def format_duration(seconds):
    """Переводит секунды в формат 1ч 20м 5с"""
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}ч {m}м {s}с"


def get_global_stats():
    """Загружает статистику. Если полей нет (старый файл), добавляет нули."""
    default_stats = {
        "total_tests": 0,
        "total_test_time_sec": 0,
        "total_uptime_sec": 0,
        "last_run": "",
    }

    if not os.path.exists(STATS_FILE):
        return default_stats

    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {**default_stats, **data}
    except Exception:
        return default_stats


def update_stats(tests_added=0, test_time_added=0, uptime_added=0):
    """
    Универсальная функция обновления статистики.
    tests_added: сколько тестов прошли (0 или 1)
    test_time_added: сколько секунд ушло на решение
    uptime_added: сколько секунд работал бот (в конце сессии)
    """
    stats = get_global_stats()

    stats["total_tests"] += tests_added
    stats["total_test_time_sec"] += test_time_added
    stats["total_uptime_sec"] += uptime_added
    stats["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=4, ensure_ascii=False)

    return stats
