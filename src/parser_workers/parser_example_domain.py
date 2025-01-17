from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dotenv import load_dotenv
from typing import Tuple
import os
load_dotenv()

# Указываем доступность для экспорта - только функцию parse
__all__ = ['parse']

# Глобальный экземпляр драйвера
driver = None
parsing_url = os.getenv("PARSE_URL")

def init_driver():
    global driver

    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Запуск в фоновом режиме
    chrome_options.add_argument("--no-sandbox")  # Отключение песочницы
    chrome_options.add_argument("--disable-dev-shm-usage")  # Для уменьшения использования памяти в контейнерах

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    
def parse(domain) -> Tuple[bool, str]:
    global parsing_url
    init_driver()

    if not parsing_url:
        return False, f"no url to parse {parsing_url}"
    
    try:
        driver.get(parsing_url)

        # Поиск поля ввода по селектору
        input_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#Check_URL"))
        )
        input_field.clear()  # Очищаем поле
        input_field.send_keys(domain)

        # Нажатие на кнопку отправки формы
        send_button = driver.find_element(By.CSS_SELECTOR, "#SendFormBut")
        send_button.click()

        results = None

        try:
            # Ожидание результата в блоке .clean .middle
            results_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".clean .middle"))
            )
            results = results_element.text
        except Exception:
            # Если не нашли в первом блоке, ищем в .blocklist
            results_element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".blocklist"))
            )
            results = results_element.text
        # Обработка результатов
        results = results.split(' ')
        result = results[0]

        if result.startswith("С"):  # Проверка на "заблокирован"
            return True, ""
        elif len(results) > 2 and results[2].startswith("в"):  # Проверка на "включен"
            return False, ""
        else:  # Проверка на "не найден"
            return False, ""

    except Exception as e:
        print(f"Произошла ошибка при парсинге {parsing_url}: {str(e)}")
        return False, f"err: {e}"
    finally:
        if driver:
            driver.quit()