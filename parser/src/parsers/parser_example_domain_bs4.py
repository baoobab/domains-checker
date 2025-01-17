from bs4 import BeautifulSoup
from dotenv import load_dotenv
from requests import get
from typing import Tuple
import os
load_dotenv()

# Указываем доступность для экспорта - только функцию parse
__all__ = ['parse']

# Глобальные настройки
parsing_url = os.getenv("PARSE_URL_2")
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36'
    }

def parse(domain) -> Tuple[bool, str]:
    global headers, parsing_url

    if not parsing_url:
        return False, f"no url to parse {parsing_url}"
    
    try:
        response = get(f"{parsing_url}{domain}", headers=headers)
                
        if response.status_code != 200:
            print("Не удалось получить данные", response)
            return False, "cannot get"

        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = soup.select('.search-info .item p')
        noted_count = 0
        result = False

        if len(results) > 1:
            noted_count = int(str(results[1]).replace("<p>", "").replace("</p>", ""))
        if noted_count > 0:
            result = True

        return result, ""
    except Exception as e:
        print(f"Произошла ошибка при парсинге: {str(e)}")
        return False, f"err: {e}"
    