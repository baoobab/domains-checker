from flask import Flask, render_template, request, redirect, url_for
from dotenv import load_dotenv
from seleniumbase import Driver
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta, timezone
import uuid
import json
import os
import threading
import queue
import atexit

# Загрузка переменных окружения из .env файла
load_dotenv()

app = Flask(__name__, template_folder="/home/runner/domains-checker/templates")

# Глобальный экземпляр драйвера
driver = Driver()
scheduler = BackgroundScheduler({'apscheduler.timezone':
                                 'UTC'})  # Таймзона стандартизорована

# Файл для хранения запланированных задач
jobs_file = os.getenv("DB_PATH")

# Создаем глобальную очередь для управления задачами
jobs_queue = queue.Queue()

# Текущий часовой пояс сервера
server_timezone = datetime.now().astimezone().tzinfo


def init_driver():
    global driver
    options = {"uc": True, "headless": True}
    driver = Driver(**options)
    driver.uc_open_with_reconnect(os.getenv("PARSE_URL"))


def shutdown_scheduler():
    """Останавливаем планировщик."""
    if scheduler.running:
        scheduler.shutdown()


def shutdown_thread():
    """Останавливаем поток обработки очереди."""
    jobs_queue.put(None)  # Отправляем сигнал завершения потоку


def unify_date(date_str, timezone_offset_str):
    """Обрабатывает строку даты и пояса и конвертирует ее в UTC."""
    try:
        date_naive = datetime.fromisoformat(date_str.strip())

        timezone_offset_str = timezone_offset_str.replace("UTC", "")
        offset_hours, offset_minutes = map(int,
                                           timezone_offset_str[1:].split(':'))
        offset = timedelta(hours=offset_hours, minutes=offset_minutes)

        date_aware = date_naive.replace(tzinfo=timezone(offset))
        utc_date = date_aware.astimezone(timezone.utc)

        return utc_date
    except Exception as e:
        print(f"Ошибка при обработке даты {date_str} {timezone_offset_str}:", e)
        return None  # Возвращаем None в случае ошибки


def parse_blocklist(domain):
    global driver

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
        else:  #(len(results) > 2 and results[2].startswith("н")): # когда results = ['Искомый', 'ресурс', 'не', 'найден'] => доступен
            results = "Available"

        return results if results else "Не удалось найти результаты."

    except Exception as e:
        return f"Произошла ошибка при парсинге: {str(e)}"


def process_queue():
    print("process_queue")
    while True:
        domain = jobs_queue.get()  # Получаем домен из очереди
        if domain is None:  # Проверка на завершение работы потока
            break

        result = parse_blocklist(domain)  # Парсим домен
        update_job_result(domain, result)  # Обновляем результат задачи
        jobs_queue.task_done()  # Указываем, что задача выполнена


@app.route("/", methods=["GET", "POST"])
def index():
    result = ""
    if request.method == "POST":
        domain = request.form["domain"]
        result = parse_blocklist(domain)
        return redirect(url_for(
            'index',
            result=result))  # Перенаправляем на ту же страницу с результатом
    return render_template("index.html", result=result)


@app.route("/cron-parser", methods=["GET", "POST"])
def cron_parser():
    jobs = load_jobs()  # Загружаем запланированные задачи

    if request.method == "POST":
        domain = request.form["domain"]
        start_date_str = request.form["start_date"]
        timezone_str = request.form[
            "timezone"]  # Получаем выбранный часовой пояс

        interval_minutes = int(
            request.form["interval"])  # Получаем интервал в минутах

        # Проверка формата даты
        try:
            client_start_date = datetime.fromisoformat(
                start_date_str)  # Преобразуем строку в объект datetime
            
            utc_start_date = unify_date(start_date_str, timezone_str)
        except ValueError:
            return render_template("cron_parser.html",
                                   message="Неверный формат даты.",
                                   jobs=jobs)

        # Проверка на существующий домен
        if any(job['domain'] == domain for job in jobs.values()):
            return render_template(
                "cron_parser.html",
                message="Задача для этого домена уже запланирована.",
                jobs=jobs)

        # Генерация уникального идентификатора для задания
        job_id = str(uuid.uuid4())  # Генерируем уникальный ID

        # Запланируем задачу с заданным интервалом и датой старта
        scheduler.add_job(func=schedule_parsing,
                          trigger='interval',
                          id=job_id,
                          args=[domain],
                          minutes=interval_minutes,
                          start_date=utc_start_date)

        # Сохраняем задачу в файл
        if utc_start_date:
            save_job(job_id, domain, utc_start_date.isoformat(), interval_minutes)
        else:
            save_job(job_id, domain, client_start_date.isoformat(), interval_minutes)

        
        # После добавления задачи обновляем список задач и возвращаем его на страницу
        jobs = load_jobs(
        )  # Загружаем обновленный список задач после добавления новой задачи

        return render_template("cron_parser.html",
                               message="Задача запланирована!",
                               jobs=jobs)

    return render_template("cron_parser.html", jobs=jobs)


@app.route("/delete-job/<job_id>", methods=["POST"])
def delete_job(job_id):
    jobs = load_jobs()

    if job_id in jobs:
        scheduler.remove_job(job_id)  # Удаляем задачу из планировщика
        del jobs[job_id]  # Удаляем задачу из списка
        with open(str(jobs_file), 'w') as f:
            json.dump(jobs, f)  # Сохраняем изменения в файл

        return redirect(
            url_for('cron_parser'))  # Перенаправляем на страницу крона

    return redirect(url_for('cron_parser'))  # Перенаправляем на страницу крона


@app.route("/edit-job/<job_id>", methods=["GET"])
def edit_job(job_id):
    jobs = load_jobs()

    if job_id in jobs:
        job = jobs[job_id]

        return render_template(
            "edit_job.html", job=job, job_id=job_id
        )  # Отправляем данные задачи на страницу редактирования

    return render_template("cron_parser.html",
                           message="Задача не найдена.",
                           jobs=jobs)


@app.route("/update-job/<job_id>", methods=["POST"])
def update_job(job_id):
    jobs = load_jobs()

    if job_id in jobs:
        start_date_str = request.form["start_date"]
        timezone_str = request.form[
        "timezone"]  # Получаем выбранный часовой пояс
        interval_minutes = int(
            request.form["interval"])  # Получаем интервал в минутах

        try:
            client_start_date = datetime.fromisoformat(
                start_date_str)  # Преобразуем строку в объект datetime

            utc_start_date = unify_date(start_date_str, timezone_str)

            if (utc_start_date):
                jobs[job_id]['start_date'] = utc_start_date.isoformat()
            else:
                jobs[job_id]['start_date'] = client_start_date.isoformat()
                
            jobs[job_id]['interval'] = interval_minutes

            # Обновляем задачу в планировщике
            scheduler.remove_job(job_id)  # Удаляем старую задачу
            scheduler.add_job(func=schedule_parsing,
                              trigger='interval',
                              id=job_id,
                              args=[jobs[job_id]['domain']],
                              minutes=interval_minutes)

            with open(str(jobs_file), 'w') as f:
                json.dump(jobs, f)  # Сохраняем изменения в файл

            return redirect(url_for(
                'cron_parser'))  # Перенаправляем на страницу со списком задач

        except ValueError:
            return render_template("edit_job.html",
                                   job=jobs[job_id],
                                   message="Неверный формат даты.")

    return redirect(
        url_for('cron_parser')
    )  # Перенаправляем на страницу со списком задач, если задача не найдена.


def schedule_parsing(domain):
    jobs_queue.put(domain)  # Добавляем домен в очередь для обработки


def save_job(job_id, domain, start_date, interval):
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


def update_job_result(domain, result):
    jobs = load_jobs()

    for job_id, job in jobs.items():
        if job['domain'] == domain:
            job['last_result'] = result  # Сохраняем результат последней проверки
            
            now_utc = datetime.now(timezone.utc) # Форматируем дату с UTC-смещением
            formatted_datetime = now_utc.strftime("%Y-%m-%dT%H:%M:00+00:00") #Форматируем дату без секунд, добавляем UTC смещение
            job['last_check'] = formatted_datetime

    with open(str(jobs_file), 'w') as f:
        json.dump(jobs, f)
    f.close()

    print(f"Парсинг {domain} выполнен в {datetime.now()}: {result}")


def load_jobs():
    if os.path.exists(str(jobs_file)):
        print("Файл существует!")
        try:
            with open(str(jobs_file), 'r') as f:
                content = f.read().strip(
                )  # Читаем содержимое и удаляем пробелы
                if not content:  # Проверяем, пустой ли файл
                    print("Файл пуст.")
                    return {}
                print("Открываем файл для чтения.")
                return json.loads(
                    content)  # Используем json.loads для обработки строки
        except json.JSONDecodeError as e:
            print(f"Ошибка при декодировании JSON: {e}")
            return {}  # Возвращаем пустой словарь в случае ошибки
        except Exception as e:
            print(f"Произошла ошибка: {e}")
            return {}  # Возвращаем пустой словарь в случае других ошибок
    print("Файл не найден.")
    return {}


def load_and_schedule_jobs():
    jobs = load_jobs()

    for job_id, job in jobs.items():
        domain = job['domain']
        start_date = datetime.fromisoformat(job['start_date'])

        # Добавляем задачу в планировщик независимо от времени начала (включая будущее)
        interval_minutes = job['interval']

        scheduler.add_job(func=schedule_parsing,
                          trigger='interval',
                          id=job_id,
                          args=[domain],
                          minutes=interval_minutes,
                          start_date=start_date)

        print(
            f"Задача {job_id} загружена и запланирована для домена {domain}.")


@app.errorhandler(Exception)
def handle_exception(e):
    return f"Произошла ошибка на сервере. Пожалуйста, попробуйте позже. {str(e)}", 500


if __name__ == "__main__":
    init_driver()

    # Запускаем планировщик только один раз при старте приложения
    if not scheduler.running:
        scheduler.start()

    # Запускаем поток для обработки очереди
    thread = threading.Thread(target=process_queue)
    thread.start()

    load_and_schedule_jobs()  # Загружаем задачи из файла в планировщик

    # Регистрация функций завершения
    atexit.register(shutdown_scheduler)
    atexit.register(shutdown_thread)

    print("Часовой пояс сервера:", server_timezone)

    try:
        app.run(os.getenv("HOST"), int(os.getenv("PORT") or 3000))
    finally:
        if driver:
            driver.quit()
