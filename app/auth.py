import os
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import app.config  # noqa: F401 - гарантирует загрузку .env до чтения переменных.


def get_credentials():
    login = os.getenv("LOGIN", "").strip()
    password = os.getenv("PASSWORD", "").strip()
    return login, password


def login_on_mudl(driver):
    try:
        login, password = get_credentials()
        if not login or not password:
            raise RuntimeError("LOGIN/PASSWORD не заданы в .env")

        print(f"URL NOW: {driver.current_url}")
        print(f"🔐 Логинимся как {login}...")

        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "username")))

        input_login = driver.find_element(By.ID, "username")
        input_login.clear()
        input_login.send_keys(login)

        time.sleep(2)

        input_password = driver.find_element(By.ID, "password")
        input_password.clear()
        input_password.send_keys(password)

        time.sleep(2)
        input_password.send_keys(Keys.ENTER)

        WebDriverWait(driver, 10).until(EC.url_contains("/my/"))
        print("✅ Успешный вход!")

    except Exception as e:
        print(f"❌ Ошибка входа: {e}")
