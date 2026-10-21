"""Worker: runs DistilBERT sentiment analysis on the text it receives."""

import os
import socket
import time

from flask import Flask, jsonify, request
from transformers import pipeline

MODEL_NAME = os.getenv("MODEL_NAME", "distilbert-base-uncased-finetuned-sst-2-english")
WORKER_NAME = os.getenv("WORKER_NAME", socket.gethostname())

# Loaded once at startup, not per request
classifier = pipeline("sentiment-analysis", model=MODEL_NAME)

app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify(status="ok", worker=WORKER_NAME, model=MODEL_NAME)


@app.post("/run_model")
def run_model():
    data = request.get_json(silent=True) or {}
    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        return jsonify(error="JSON body must contain a non-empty 'text' string"), 400

    start = time.perf_counter()
    result = classifier(text, truncation=True)[0]
    return jsonify(
        worker=WORKER_NAME,
        model=MODEL_NAME,
        input=text,
        label=result["label"],
        score=round(result["score"], 4),
        inference_ms=round((time.perf_counter() - start) * 1000, 1),
    )
