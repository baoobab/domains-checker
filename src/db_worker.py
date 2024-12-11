from flask import Flask, request, jsonify
from datetime import datetime, timezone
import json
from dotenv import load_dotenv
import os

load_dotenv()

# Файл для хранения запланированных задач
jobs_file = os.getenv("DB_PATH")

app = Flask(__name__)

@app.route("/remove-job", methods=["POST"])
def remove_job_route():
    job_id = request.json.get('job_id')
    
    if not job_id:
        return jsonify({"success": False})
    
    remove_job(job_id)
    return jsonify({"success": True})

def remove_job(job_id):
    jobs = load_jobs()
    
    if job_id in jobs:
        del jobs[job_id]  # Удаляем задачу из списка
        with open(str(jobs_file), 'w') as f:
            json.dump(jobs, f)  # Сохраняем изменения в файл


@app.route("/update-job-result", methods=["POST"])
def update_job_result_route():
    domain = request.json.get('domain')
    result = request.json.get('result')

    if not domain or not result:
        return jsonify({"success": False})

    update_job_result(domain, result)
    return jsonify({"success": True})

def update_job_result(domain, result):
    jobs = load_jobs()

    for job_id, job in jobs.items():
        if job['domain'] == domain:
            job['last_result'] = result  # Сохраняем результат последней проверки

            now_utc = datetime.now(
                timezone.utc)  # Форматируем дату с UTC-смещением
            formatted_datetime = now_utc.strftime(
                "%Y-%m-%dT%H:%M:00+00:00"
            )  #Форматируем дату без секунд, добавляем UTC смещение
            job['last_check'] = formatted_datetime

    with open(str(jobs_file), 'w') as f:
        json.dump(jobs, f)
    f.close()

@app.route("/update-job", methods=["POST"])
def update_job_route():
    job_id = request.json.get('job_id')
    start_date = request.json.get('start_date')
    interval_hours = request.json.get('interval_hours')

    if not job_id or not start_date or not interval_hours:
        return jsonify({"success": False})

    update_job(job_id, start_date, interval_hours)
    return jsonify({"success": True})

def update_job(job_id, start_date, interval_hours):
    jobs = load_jobs()

    if job_id in jobs:
        job = jobs[job_id]

        job['start_date'] = start_date
        job['interval'] = interval_hours

    with open(str(jobs_file), 'w') as f:
        json.dump(jobs, f)
    f.close()

@app.route("/get-jobs", methods=["GET"])
def get_jobs():
    return jsonify({"jobs": load_jobs()})

def load_jobs():
    if os.path.exists(str(jobs_file)):
        print("File exists!")
        try:
            with open(str(jobs_file), 'r') as f:
                content = f.read().strip(
                )  # Читаем содержимое и удаляем пробелы
                if not content:  # Проверяем, пустой ли файл
                    print("The file is empty.")
                    return {}
                print("Open for read")
                return json.loads(
                    content)  # Используем json.loads для обработки строки
        except json.JSONDecodeError as e:
            print(f"JSON decode err: {e}")
            return {}  # Возвращаем пустой словарь в случае ошибки
        except Exception as e:
            print(f"File err: {e}")
            return {}  # Возвращаем пустой словарь в случае других ошибок
    print("File not found.")
    return {}

@app.route("/add-job", methods=["POST"])
def add_job_route():
    job_id = request.json.get('job_id')
    domain = request.json.get('domain')
    interval_hours = request.json.get('interval_hours')
    start_date = request.json.get('start_date')

    if not job_id or not domain or not interval_hours or not start_date:
        return jsonify({"success": False})
    
    add_job(job_id, domain, start_date, interval_hours)
    return jsonify({"success": True})
    
def add_job(job_id, domain, start_date, interval):
    jobs = load_jobs()
    jobs[job_id] = {
        'domain': domain,
        'start_date': start_date,
        'interval': interval,
        'last_result': None,
        'last_check': None,
    }

    with open(str(jobs_file), 'w') as f:
        json.dump(jobs, f)


@app.errorhandler(Exception)
def handle_exception(e):
    return f"Err on db worker: {str(e)}", 500

if __name__ == '__main__':
    app.run(port=os.getenv("DB_WORKER_APP_PORT", 5003))  # Порт для бд-воркера