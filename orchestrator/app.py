import json
import os
import threading
import time
from collections import deque

import requests
from flask import Flask, jsonify, request

STATUS_PATH = os.getenv("STATUS_PATH", "data/status.json")
WORKER_ENDPOINT = "/run_model"
WORKER_TIMEOUT = 120

app = Flask(__name__)
lock = threading.Lock()
queue = deque()


class QueuedRequest:
    def __init__(self):
        self.ready = threading.Event()
        self.worker = None


def read_status():
    with open(STATUS_PATH) as f:
        return json.load(f)


def write_status(status):
    tmp_path = STATUS_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(status, f, indent=2)
    os.replace(tmp_path, STATUS_PATH)


def acquire_worker():
    with lock:
        status = read_status()
        for name, worker in status.items():
            if worker["status"] == "free":
                worker["status"] = "busy"
                write_status(status)
                return name, worker, False

        waiting = QueuedRequest()
        queue.append(waiting)
        app.logger.info("Both workers busy, request queued (queue length %d)", len(queue))

    waiting.ready.wait()
    return *waiting.worker, True


def release_worker(name):
    with lock:
        status = read_status()
        if queue:
            waiting = queue.popleft()
            waiting.worker = (name, status[name])
            waiting.ready.set()
        else:
            status[name]["status"] = "free"
            write_status(status)


def reset_status():
    with lock:
        status = read_status()
        for worker in status.values():
            worker["status"] = "free"
        write_status(status)


@app.route("/new_request", methods=["POST"])
def new_request():
    data = request.get_json(silent=True)
    if data is None:
        return jsonify(error="Request body must be JSON"), 400

    start_time = time.time()
    name, worker, was_queued = acquire_worker()
    queue_wait = time.time() - start_time

    try:
        response = requests.post(
            f"http://{worker['ip']}:{worker['port']}{WORKER_ENDPOINT}",
            json=data,
            timeout=WORKER_TIMEOUT,
        )
        body, code = response.json(), response.status_code
    except Exception as e:
        body, code = {"error": f"{name} failed: {e}"}, 502
    finally:
        release_worker(name)

    return jsonify(
        handled_by=name,
        queued=was_queued,
        queue_wait_ms=round(queue_wait * 1000, 1),
        total_ms=round((time.time() - start_time) * 1000, 1),
        worker_response=body,
    ), code


@app.route("/status", methods=["GET"])
def get_status():
    with lock:
        return jsonify(workers=read_status(), queue_length=len(queue))


reset_status()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)