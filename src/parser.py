from flask import Flask, request, jsonify
from seleniumbase import Driver
import os
from dotenv import load_dotenv

load_dotenv()

# Глобальный экземпляр драйвера
driver = Driver()
app = Flask(__name__)

def init_driver():
    global driver
    options = {"uc": True, "headless": True}
    driver = Driver(**options)
    driver.uc_open_with_reconnect(os.getenv("PARSE_URL"))

    print("driver inited")


def parse_blocklist(domain):
    try:
        driver.refresh()

        input_field = driver.find_element("#Check_URL")
        input_field.clear()  # Очищаем поле
        input_field.send_keys(domain)
        driver.click("#SendFormBut")

        results = None

        try:
            driver.wait_for_element(".clean .middle", timeout=10)
            results = driver.get_text(".clean .middle")
        except Exception:
            driver.wait_for_element(".blocklist", timeout=5)
            results = driver.get_text(".blocklist")

        results = results.split(' ')
        result = results[0]
        if (
                result.startswith("С")
        ):  # когда results = ['Состояние:', 'заблокирован\nIP-адрес:'] => блокнут
            results = "Blocked"
        elif (len(results) > 2 and results[2].startswith("в")
              ):  # когда results = ['Искомый', 'ресурс', 'включен'] => блокнут
            results = "Blocked"
        else:  # когда results = ['Искомый', 'ресурс', 'не', 'найден'] => доступен
            results = "Available"

        return results if results else "No results"

    except Exception as e:
        return f"Parsing err: {str(e)}"
    

@app.route("/parse", methods=["POST"])
def parse_route():
    domain = request.json.get('domain')

    if not domain:
        return jsonify({"result": None})
    
    result = parse_blocklist(domain)
    print("Result for", domain, result)
    return jsonify({"result": f"{result}"})


@app.errorhandler(Exception)
def handle_exception(e):
    return f"Err on parser: {str(e)}", 500

if __name__ == '__main__':
    init_driver()
    app.run(port=os.getenv("PARSER_APP_PORT", 5004))  # Порт для парсера

