FROM python:3.12-slim

WORKDIR /app

# CPU-only PyTorch: the CUDA build is several GB and t2.large has no GPU
RUN pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download the model at build time so the container starts without network access
ENV HF_HOME=/app/hf-cache
ENV MODEL_NAME=distilbert-base-uncased-finetuned-sst-2-english
RUN python -c "from transformers import pipeline; pipeline('sentiment-analysis', model='${MODEL_NAME}')"

COPY app.py .

EXPOSE 5000
# One process, one thread: a worker handles one request at a time, the orchestrator does the queueing
CMD ["gunicorn", "--workers", "1", "--threads", "1", "--timeout", "120", "--bind", "0.0.0.0:5000", "app:app"]
