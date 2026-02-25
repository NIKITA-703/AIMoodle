"""Совместимость со старым импортом bot_logic.
Вся логика вынесена по модулям: config/auth/course_flow/lecture_flow/test_flow/stats.
"""

from app.config import (
    COOKIES_FILE,
    STATS_FILE,
    driver_path,
    options,
    rand_user_agent,
    service,
    url_home_page,
    url_login,
)
from app.stats import format_duration, get_global_stats, update_stats
from app.browser_utils import sanitize_filename, wait_for_element
from app.auth import login_on_mudl
from app.flows.course_flow import find_current_test_info, get_current_course_link
from app.flows.lecture_flow import find_lecture_url, save_page_html, try_get_lecture_via_breadcrumbs
from app.flows.test_flow import extract_answers, parse_results, solve_active_test, start_test_attempt, submit_test

__all__ = [
    "COOKIES_FILE",
    "STATS_FILE",
    "driver_path",
    "options",
    "rand_user_agent",
    "service",
    "url_home_page",
    "url_login",
    "format_duration",
    "get_global_stats",
    "update_stats",
    "sanitize_filename",
    "wait_for_element",
    "login_on_mudl",
    "find_current_test_info",
    "get_current_course_link",
    "find_lecture_url",
    "save_page_html",
    "try_get_lecture_via_breadcrumbs",
    "extract_answers",
    "parse_results",
    "solve_active_test",
    "start_test_attempt",
    "submit_test",
]
