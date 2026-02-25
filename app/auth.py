import time
import os

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

login = os.getenv("LOGIN", "").strip()
password = os.getenv("PASSWORD", "").strip()


def login_on_mudl(driver):
    try:
        if not login or not password:
            raise RuntimeError("LOGIN/PASSWORD не заданы в .env")

        print(f"URL NOW: {driver.current_url}")
        # print(f"Logins....\n")

        print(f"🔐 Логинимся как {login}...")

        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, 'username')))

        """
            If username is the value of class attribute:
            login = driver.find_element(By.CLASS_NAME, "username")
    
            If username is the value of id attribute:
            login = driver.find_element(By.ID, "username")
    
            If username is the value of id attribute:
            login = driver.find_element(By.NAME, "username")
    
            If username is the value of linktext attribute:
            login = driver.find_element(By.LINK_TEXT, "username")
        """

        input_login = driver.find_element(By.ID, 'username')
        input_login.clear()
        input_login.send_keys(login)

        time.sleep(2)

        input_password = driver.find_element(By.ID, 'password')
        input_password.clear()
        input_password.send_keys(password)

        time.sleep(2)

        input_password.send_keys(Keys.ENTER)

        # time.sleep(7)
        # driver.get(url_home_page)

        # Ждём перехода на домашнюю страницу
        WebDriverWait(driver, 10).until(
            EC.url_contains("/my/")
        )
        print("✅ Успешный вход!")

    except Exception as e:
        print(f"❌ Ошибка входа: {e}")
