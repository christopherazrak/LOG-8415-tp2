FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .

EXPOSE 80
# Exactly one process: the queue and the lock live in memory and must be shared by all requests.
# Threads let many requests wait in the queue at the same time.
CMD ["gunicorn", "--workers", "1", "--threads", "32", "--timeout", "300", "--bind", "0.0.0.0:80", "app:app"]
