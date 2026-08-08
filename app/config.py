import os
from pathlib import Path

from selenium import webdriver


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        pass


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
ENV_PATH = BASE_DIR / ".env"

BOT_VERSION = "3.2.0"
MEMORY_VERSION = "review-v2"
CONTEXT_VERSION = "lexical-v2-progressive"

DATA_DIR.mkdir(exist_ok=True)
_load_env_file(ENV_PATH)

COOKIES_FILE = DATA_DIR / "moodle_cookies.pkl"
STATS_FILE = DATA_DIR / "global_stats.json"
BOT_HISTORY_FILE = DATA_DIR / "bot_history.log"
QUIZ_MEMORY_FILE = DATA_DIR / "quiz_memory.json"
DATABASE_FILE = DATA_DIR / "bot.db"
LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234").rstrip("/")
TARGET_COURSE = os.getenv("TARGET_COURSE", "").strip()
AUTO_USE_LAST_ATTEMPT = os.getenv("AUTO_USE_LAST_ATTEMPT", "false").strip().lower() in {
    "1", "true", "yes", "on"
}
REQUIRE_LECTURE_CONTEXT = os.getenv("REQUIRE_LECTURE_CONTEXT", "false").strip().lower() in {
    "1", "true", "yes", "on"
}
AI_ENABLE_THINKING = os.getenv("AI_ENABLE_THINKING", "false").strip().lower() in {
    "1", "true", "yes", "on"
}
REFRESH_COMPLETED_COURSES = os.getenv(
    "REFRESH_COMPLETED_COURSES", "false"
).strip().lower() in {"1", "true", "yes", "on"}
try:
    COURSE_CACHE_DAYS = max(1, int(os.getenv("COURSE_CACHE_DAYS", "30")))
except ValueError:
    COURSE_CACHE_DAYS = 30
try:
    TESTS_LIMIT = max(1, int(os.getenv("TESTS_LIMIT", "1")))
except ValueError:
    TESTS_LIMIT = 1
try:
    PARALLEL_WORKERS = min(4, max(1, int(os.getenv("PARALLEL_WORKERS", "1"))))
except ValueError:
    PARALLEL_WORKERS = 1
try:
    AI_MAX_CONCURRENT_REQUESTS = min(
        4, max(1, int(os.getenv("AI_MAX_CONCURRENT_REQUESTS", "1")))
    )
except ValueError:
    AI_MAX_CONCURRENT_REQUESTS = 1
try:
    AI_RESPONSE_ATTEMPTS = min(3, max(1, int(os.getenv("AI_RESPONSE_ATTEMPTS", "2"))))
except ValueError:
    AI_RESPONSE_ATTEMPTS = 2

options = webdriver.ChromeOptions()
options.add_argument("--window-size=1590,950")

chrome_binary_path = os.getenv("CHROME_BINARY_PATH", "").strip()
if chrome_binary_path:
    options.binary_location = chrome_binary_path

url_home_page = "https://lms.mitu.msk.ru/my/"
url_login = "https://lms.mitu.msk.ru/login/index.php"
