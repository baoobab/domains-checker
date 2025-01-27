from flask import Flask, request, jsonify
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
import os
import requests
import sys
import signal

load_dotenv()

app = Flask(__name__)
scheduler = BackgroundScheduler({'apscheduler.timezone': 'UTC'})

QUEUE_WORKER_URL = os.getenv("TASKS_QUEUE_APP_URL") # URL воркера очереди


def start_scheduler():
    scheduler.start()
    print("Scheduler started")

def stop_scheduler(signum, frame):
    scheduler.shutdown(wait=False)
    print("Scheduler stopped")
    sys.exit(0)

@app.route('/add-job', methods=['POST'])
def add_job_route():
    job_id = request.json.get('job_id')
    domain = request.json.get('domain')
    interval_hours = request.json.get('interval_hours')
    start_date = request.json.get('start_date')

    if not job_id or not domain or not interval_hours or not start_date:
        return jsonify({"success": False})
    
    add_job(job_id, domain, interval_hours, start_date)
    return jsonify({"success": True})

def add_job(job_id, domain, interval_hours, start_date):
    # Запланируем задачу с заданным интервалом и датой старта
    scheduler.add_job(func=schedule_parsing,
                        trigger='interval',
                        id=job_id,
                        args=[domain],
                        hours=interval_hours,
                        start_date=start_date)
            

@app.route('/remove-job', methods=['POST'])
def remove_job_route():
    job_id = request.json.get('job_id')
    
    remove_job(job_id)
    return jsonify({"success": True})

def remove_job(job_id):
    # Удалите задание из планировщика
    scheduler.remove_job(job_id)

def schedule_parsing(domain):
    try:
        print("Pinned queue for", domain)
        requests.post(f"{QUEUE_WORKER_URL}/add-job", json={'domain': domain})
    except Exception as e:
        print("Scheduler err while send to queue:", str(e))


@app.errorhandler(Exception)
def handle_exception(e):
    return f"Err on scheduler: {str(e)}", 500

if __name__ == "__main__":
    signal.signal(signal.SIGINT, stop_scheduler)  # Обработка сигнала завершения
    start_scheduler()
    
    app.run(host="0.0.0.0", port=os.getenv("PORT", 5001))  # Порт для планировщика
    
