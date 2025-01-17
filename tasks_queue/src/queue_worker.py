from flask import Flask, request, jsonify
import queue
import requests
import threading
import os
from dotenv import load_dotenv
import signal
import sys

load_dotenv()

app = Flask(__name__)

PARSER_URL = os.getenv("PARSER_APP_URL") # URL приложения-парсера
DB_URL = os.getenv("DB_APP_URL") # URL приложения-бд
SMTP_MAIL_URL = os.getenv("SMTP_MAILER_APP_URL") # URL приложения-рассыльщика

# Создаем глобальную очередь для управления задачами
jobs_queue = queue.Queue()

# Создаем глобальную очередь для управления рассылкой писем
mails_queue = queue.Queue()


def stop_threads(signum, frame):
    jobs_queue.put(None)  # Отправляем сигнал завершения потоку
    mails_queue.put(None)  # Отправляем сигнал завершения потоку

    print("Queue's stopped")
    sys.exit(0)

def process_jobs_queue():
    while True:
        domain = jobs_queue.get()  # Получаем домен из очереди
        if domain is None:  # Проверка на завершение работы потока
            break
        
        print("Pinned parser for", domain)
        response = requests.post(f"{PARSER_URL}/parse", json={'domain': domain})
        result = response.json()

        if result['result'] == "Blocked":
            mails_queue.put(
                domain
            )  # Все блокнутые домены отправляем в очередь для рассылки

        print("Pinned db for", domain)
        requests.post(f"{DB_URL}/update-job-result", json={'domain': domain, 'result': result})

        jobs_queue.task_done()  # Указываем, что задача выполнена


def process_mails_queue():
    while True:
        domain = mails_queue.get()  # Получаем домен из очереди
        if domain is None:  # Проверка на завершение работы потока
            break
        
        print("Pinned smtp for", domain)
        requests.post(f"{SMTP_MAIL_URL}/send-email", json={'subject': 'Домен заблокирован', 'body': f'Домен {domain} заблокирован'})

        mails_queue.task_done()  # Указываем, что задача выполнена


@app.route("/add-job", methods=["POST"])
def add_job_route():
    domain = request.json.get('domain')

    if not domain:
        return jsonify({"success": False})
    
    add_job(domain)

    return jsonify({"success": True})

def add_job(domain):
    jobs_queue.put(domain)  # Добавляем домен в очередь для обработки


@app.errorhandler(Exception)
def handle_exception(e):
    return f"Err on queue worker: {str(e)}", 500

if __name__ == "__main__":
    signal.signal(signal.SIGINT, stop_threads) # Обработка сигнала завершения
    # Запускаем поток для обработки очереди
    jobsThread = threading.Thread(target=process_jobs_queue)
    jobsThread.start()
    print("Jobs Queue started")

    # Запускаем поток для обработки очереди
    mailsThread = threading.Thread(target=process_mails_queue)
    mailsThread.start()
    print("Mails Queue started")

    app.run(host=os.getenv("HOST", "localhost"), port=os.getenv("PORT", 5002)) # Порт для воркера очередей