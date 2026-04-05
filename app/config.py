import os
import random
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.service import Service


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
DRIVERS_DIR = BASE_DIR / "drivers"
ENV_PATH = BASE_DIR / ".env"

DATA_DIR.mkdir(exist_ok=True)
DRIVERS_DIR.mkdir(exist_ok=True)
_load_env_file(ENV_PATH)

USER_AGENT_FILE = DATA_DIR / "user_agent.txt"
COOKIES_FILE = DATA_DIR / "moodle_cookies.pkl"
STATS_FILE = DATA_DIR / "global_stats.json"
BOT_HISTORY_FILE = DATA_DIR / "bot_history.log"

options = webdriver.ChromeOptions()
options.add_argument("-window-size=1590,950")
options.binary_location = os.getenv(
    "CHROME_BINARY_PATH",
    r"C:\Users\NIKITA\Downloads\chrome-win64(1)\chrome-win64\chrome.exe",
)

try:
    with open(USER_AGENT_FILE, "r", encoding="utf-8") as f:
        user_agents = [line.strip() for line in f if line.strip()]
    rand_user_agent = random.choice(user_agents)
    options.add_argument(f"user-agent={rand_user_agent}")
except Exception:
    rand_user_agent = "unknown"

driver_path = os.getenv("CHROMEDRIVER_PATH", str(DRIVERS_DIR / "chromedriver.exe"))
service = Service(driver_path)

url_home_page = "https://lms.mitu.msk.ru/my/"
url_login = "https://lms.mitu.msk.ru/login/index.php"
