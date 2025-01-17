import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from flask import Flask, request, jsonify
import os
import signal
import sys

load_dotenv()

app = Flask(__name__)

# Функция для отправки письма
def send_email(subject, body):
    sender_email = os.getenv('SMTP_FROM')
    receiver_email = os.getenv('SMTP_TO')
    password = os.getenv('SMTP_PASSWORD')
    smtp_host = os.getenv('SMTP_HOST')
    smtp_port = os.getenv('SMTP_PORT')

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))
    try:
        if not password or not sender_email or not receiver_email or not smtp_host or not smtp_port:
            raise Exception()
        with smtplib.SMTP(smtp_host, int(smtp_port)) as server:
            server.starttls()  # Защита соединения
            server.login(sender_email, password)  # Логин на почтовом сервере
            server.send_message(msg)  # Отправка сообщения
        print("Email sent")
    except Exception as e:
        print(f"Smtp err: {e}")

@app.route("/send-email", methods=["POST"])
def send_email_route():
    subject = request.json.get('subject')
    body = request.json.get('body')

    if not subject or not body:
        return jsonify({"success": False})
    
    send_email(subject, body)
    return jsonify({"success": True})

def stop_mailer(signum, frame):
    print("Mailer stopped")
    sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, stop_mailer)  # Обработка сигнала завершения

    app.run(host=os.getenv("HOST", "localhost"), port=os.getenv("PORT", 5005))  # Порт для smtp-рассыльщика