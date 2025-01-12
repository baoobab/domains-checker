from flask import Flask, request, jsonify
from parser_workers.parser_example_domain_bs4 import parse as p1
from parser_workers.parser_example_domain import parse as p2
from dotenv import load_dotenv
from typing import Tuple
import os
load_dotenv()

app = Flask(__name__)
parsers = [p1, p2] # Доступные парсеры (TODO: глобальный скоуп такое, потом вынести)

def parse_blocklist(domain) -> str:
    global parsers

    errors_string = "" # стркоа для возврата ошибок, конкатится к результату
    for p_func in parsers:
        p_result, p_error = p_func(domain=domain)
        if p_result:
            return f"Blocked{errors_string}" # Одного вхождения достаточно - возвращаем
        if p_error:
            errors_string += f" error: {p_error}"
    return f"Available{errors_string}"

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
    app.run(port=os.getenv("PARSER_APP_PORT", 5004))  # Порт для парсера

