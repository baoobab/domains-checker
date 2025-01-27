FROM python:3.11

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN addgroup --system --gid 1001 flaskpy
RUN adduser --system --uid 1001 flaskpy
USER flaskpy

CMD ["python", "src/parser_worker.py"]
