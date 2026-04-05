from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def sanitize_filename(name):
    return "".join([c if c.isalnum() or c in " ._-" else "_" for c in name]).strip()


def wait_for_element(driver: webdriver.Chrome, locator: tuple, timeout: float = 10) -> None:
    """Ожидает появления элемента на странице."""
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located(locator))
    except TimeoutException:
        print(f"Элемент не найден после {timeout} секунд.")
        raise
