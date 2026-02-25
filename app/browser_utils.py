from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def sanitize_filename(name):
    return "".join([c if c.isalnum() or c in " ._-" else "_" for c in name]).strip()
    """Удаляет запрещенные символы из имени файла/папки."""

def wait_for_element(driver: webdriver.Chrome, locator: tuple, timeout: float = 10) -> None:
    """Ожидает появления элемента на странице.
    Args:
        driver: Экземпляр веб-драйвера Selenium.
        locator: Кортеж, содержащий тип локатора (By.ID, By.XPATH и т.д.) и значение локатора.
        timeout: Максимальное время ожидания в секундах.
    Raises:
        TimeoutException: Если элемент не появился в течение указанного времени.
    """
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located(locator))
    except TimeoutException:
        print(f"Элемент не найден после {timeout} секунд.")
        raise
    # Пример использования:
    # wait_for_element(driver, (By.ID, "myDynamicElement")) #ожидание присутствия элемента
    # wait_for_element(driver, (By.XPATH, "//div[@class='loaded']")) #ожидание присутствия элемента
    # wait_for_element(driver, (By.CLASS_NAME, "some-class"), timeout=5) # Установка таймаута в 5 секунд

