import os
import socket
import time

from flask import Flask, jsonify, request
from transformers import pipeline

MODEL_NAME = os.getenv("MODEL_NAME", "distilbert-base-uncased-finetuned-sst-2-english")
WORKER_NAME = os.getenv("WORKER_NAME", socket.gethostname())

classifier = pipeline("sentiment-analysis", model=MODEL_NAME)

app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health():
    return jsonify(status="ok", worker=WORKER_NAME, model=MODEL_NAME)


@app.route("/run_model", methods=["POST"])
def run_model():
    data = request.get_json(silent=True) or {}
    text = data.get("text")
    
    if not isinstance(text, str) or not text.strip():
        return jsonify(error="JSON body must contain a non-empty 'text' string"), 400

    start_time = time.time()
    result = classifier(text, truncation=True)[0]
    inference_time = (time.time() - start_time) * 1000
    
    return jsonify(
        worker=WORKER_NAME,
        model=MODEL_NAME,
        input=text,
        label=result["label"],
        score=round(result["score"], 4),
        inference_ms=round(inference_time, 1),
    )