from flask import Flask, render_template, request, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import uuid
import os
import requests


# Загрузка переменных окружения из .env файла
load_dotenv()

app = Flask(__name__, template_folder=os.getenv("FLASK_TEMPLATE_FOLDER"))
app.secret_key = os.getenv('SECRET_KEY')
app.config['SESSION_COOKIE_SECURE'] = False # Использовать только через HTTPS

# URL-ы для обращения к воркерам
PARSER_URL = os.getenv("PARSER_APP_URL") # URL парсера
SCHEDULER_URL = os.getenv("SCHEDULER_APP_URL")  # URL планировщика
DB_URL = os.getenv("DB_APP_URL")  # URL бд

# Текущий часовой пояс сервера
server_timezone = datetime.now().astimezone().tzinfo

# Настройка Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)


# Модель пользователя
class User(UserMixin):

    def __init__(self, username):
        self.username = username

    def get_id(self):
        return self.username  # Возвращаем имя пользователя как уникальный идентификатор


@login_manager.user_loader
def load_user(username):
    if username == os.getenv('ADMIN_USERNAME'):
        return User(username)
    return None

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username == os.getenv('ADMIN_USERNAME') and password == os.getenv(
                'ADMIN_PASSWORD'):
            user = User(username)
            login_user(user)
            return redirect(url_for('index'))

    return '''
        <form method="post">
            Имя пользователя: <input type="text" name="username"><br>
            Пароль: <input type="password" name="password"><br>
            <input type="submit" value="Войти">
        </form>
    '''


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

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
        print(f"Ошибка при обработке даты {date_str} {timezone_offset_str}:",
              e)
        return None  # Возвращаем None в случае ошибки

@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    result = ""
    if request.method == "POST":
        domain = request.form["domain"]
        try:
            result = requests.post(f"{PARSER_URL}/parse", json={'domain': domain})
        except Exception as e:
            print("Err while try to parse:", str(e))

        return redirect(url_for(
            'index',
            result=result))  # Перенаправляем на ту же страницу с результатом
    return render_template("index.html", result=result)


@app.route("/cron-parser", methods=["GET", "POST"])
@login_required
def cron_parser():
    jobs = {}

    try:
        jobs = (requests.get(f"{DB_URL}/get-jobs"))["jobs"]  # Загружаем запланированные задачи
    except Exception as e:
        return render_template("cron_parser.html",
            message="Ошибка при получении данных из бд",
            jobs=[])


    if request.method == "POST":
        domain = request.form["domain"]
        start_date_str = request.form["start_date"]
        timezone_str = request.form[
            "timezone"]  # Получаем выбранный часовой пояс

        interval_hours = int(
            request.form["interval"])  # Получаем интервал

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

        # Сохраняем задачу
        try:
            date_to_post = client_start_date
            if utc_start_date: 
                date_to_post = utc_start_date

            schedulerResult = requests.post(f"{SCHEDULER_URL}/add-job", 
                                 json={
                                     'job_id': job_id,
                                     'domain': domain,
                                     'interval_hours': interval_hours,
                                     'start_date': date_to_post,
                                       })
            
            if not schedulerResult or schedulerResult["success"] == False:
                raise Exception
            
            dbResult = requests.post(f"{DB_URL}/add-job", 
                                 json={
                                     'job_id': job_id,
                                     'domain': domain,
                                     'interval_hours': interval_hours.isoformat(),
                                     'start_date': date_to_post,
                                       })
            
            if not dbResult or dbResult["success"] == False:
                raise Exception
            
        except Exception as e:
            return render_template("cron_parser.html",
                message="Ошибка при сохранении данных",
                jobs=jobs)

        # После добавления задачи обновляем список задач и возвращаем его на страницу
        try:
            jobs = (requests.get(f"{DB_URL}/get-jobs"))["jobs"]  # Загружаем запланированные задачи
        except Exception as e:
            return render_template("cron_parser.html",
                message="Ошибка при получении данных из бд",
                jobs=[])
    
        return render_template("cron_parser.html",
                               message="Задача запланирована!",
                               jobs=jobs)

    return render_template("cron_parser.html", jobs=jobs)


@app.route("/delete-job/<job_id>", methods=["POST"])
@login_required
def delete_job(job_id):
    requests.post(f"{SCHEDULER_URL}/remove-job", json={'job_id': job_id})
    requests.post(f"{DB_URL}/remove-job", json={'job_id': job_id})

    return redirect(
        url_for('cron_parser'))  # Перенаправляем на страницу крона


@app.route("/edit-job/<job_id>", methods=["GET"])
@login_required
def edit_job(job_id):
    jobs = {}

    try:
        jobs = (requests.get(f"{DB_URL}/get-jobs"))["jobs"]  # Загружаем запланированные задачи
    except Exception as e:
        return render_template("cron_parser.html",
            message="Ошибка при получении данных из бд")
    
    if job_id in jobs:
        job = jobs[job_id]

        return render_template(
            "edit_job.html", job=job, job_id=job_id
        )  # Отправляем данные задачи на страницу редактирования

    return render_template("cron_parser.html",
                           message="Задача не найдена.",
                           jobs=jobs)


@app.route("/update-job/<job_id>", methods=["POST"])
@login_required
def update_job(job_id):
    jobs = {}

    try:
        jobs = (requests.get(f"{DB_URL}/get-jobs"))["jobs"]  # Загружаем запланированные задачи
    except Exception as e:
        return render_template("cron_parser.html",
            message="Ошибка при получении данных из бд")

    if job_id in jobs:
        start_date_str = request.form["start_date"]
        timezone_str = request.form[
            "timezone"]  # Получаем выбранный часовой пояс
        interval_hours = int(
            request.form["interval"])  # Получаем интервал

        try:
            client_start_date = datetime.fromisoformat(
                start_date_str)  # Преобразуем строку в объект datetime

            utc_start_date = unify_date(start_date_str, timezone_str)


            date_to_post = client_start_date.isoformat()
            if (utc_start_date):
                date_to_post = utc_start_date.isoformat()

            # Обновляем задачу в планировщике
            requests.post(f"{SCHEDULER_URL}/remove-job", json={'job_id': job_id})
            
            schedulerResult = requests.post(f"{SCHEDULER_URL}/add-job", 
                                    json={
                                        'job_id': job_id,
                                        'domain': jobs[job_id]['domain'],
                                        'interval_hours': interval_hours,
                                        'start_date': date_to_post,
                                        })
                
            if not schedulerResult or schedulerResult["success"] == False:
                raise Exception

            # Обновляем задачу в бд
            requests.post(f"{DB_URL}/update-job", json={
                'job_id': job_id,
                'start_date': jobs[job_id]['start_date'],
                'interval_hours': jobs[job_id]['interval_hours'],
                })

            return redirect(url_for(
                'cron_parser'))  # Перенаправляем на страницу со списком задач

        except ValueError:
            return render_template("edit_job.html",
                job=jobs[job_id],
                message="Неверный формат даты.")
        except Exception as e:
            return render_template("edit_job.html",
                job=jobs[job_id],
                message="Непредвиденная ошибка")

    return redirect(
        url_for('cron_parser')
    )  # Перенаправляем на страницу со списком задач, если задача не найдена.


def load_and_schedule_jobs():
    jobs = {}

    try:
        response = (requests.get(f"{DB_URL}/get-jobs"))  # Загружаем запланированные задачи
        jobs = (response.json())["jobs"]

    except Exception as e:
        print("load_and_schedule_jobs db get err:", str(e))

    for job_id, job in jobs.items():
        domain = job['domain']
        start_date = job['start_date']
        interval_hours = job['interval']

        # Добавляем задачу в планировщик независимо от времени начала (включая будущее)

        try:
            requests.post(f"{SCHEDULER_URL}/add-job", 
                json={
                    'job_id': job_id,
                    'domain': domain,
                    'interval_hours': interval_hours,
                    'start_date': start_date,
                })

        except Exception as e:
            print("load_and_schedule_jobs scheduler add err:", str(e))

        print(f"Job {job_id} loaded and planned for {domain}.")


@app.errorhandler(Exception)
def handle_exception(e):
    return f"Произошла ошибка на сервере. Пожалуйста, попробуйте позже. {str(e)}", 500


if __name__ == "__main__":
    load_and_schedule_jobs()  # Загружаем задачи из файла в планировщик

    print("Server Time Zone:", server_timezone)

    try:
        app.run(host="0.0.0.0", port=os.getenv("PORT", 5000))
    except Exception as e:
        print("App err:", str(e))