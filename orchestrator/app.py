"""Orchestrator: forwards each request to a free worker, or queues it until one becomes free.

Worker state lives in status.json ({"worker1": {"ip", "port", "status"}, ...}). Every
change goes through `lock`, so two requests can never pick the same free worker.
When a worker finishes, it is handed directly to the oldest queued request (it stays
"busy"); it is only marked "free" when the queue is empty.
"""

import json
import os
import threading
import time
from collections import deque

import requests
from flask import Flask, jsonify, request

STATUS_PATH = os.getenv("STATUS_PATH", "data/status.json")
WORKER_ENDPOINT = "/run_model"
WORKER_TIMEOUT = 120  # seconds

app = Flask(__name__)
lock = threading.Lock()  # guards status.json and the queue
queue = deque()  # waiting requests, oldest first


class QueuedRequest:
    """A request waiting for a worker; release_worker() fills in `worker` and sets `ready`."""

    def __init__(self):
        self.ready = threading.Event()
        self.worker = None


def read_status():
    with open(STATUS_PATH) as f:
        return json.load(f)


def write_status(status):
    # Write to a temp file then rename, so a reader never sees a half-written file
    tmp_path = STATUS_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(status, f, indent=2)
    os.replace(tmp_path, STATUS_PATH)


def acquire_worker():
    """Return (name, worker) of a free worker, marked busy. Waits in the queue if none is free."""
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

    # Outside the lock, so release_worker() can run while we wait
    waiting.ready.wait()
    return *waiting.worker, True


def release_worker(name):
    """Give the worker to the oldest queued request, or mark it free if nobody is waiting."""
    with lock:
        status = read_status()
        if queue:
            waiting = queue.popleft()
            waiting.worker = (name, status[name])  # stays "busy"
            waiting.ready.set()
        else:
            status[name]["status"] = "free"
            write_status(status)


def reset_status():
    # A worker left "busy" by a previous run (crash, restart) would never be released
    with lock:
        status = read_status()
        for worker in status.values():
            worker["status"] = "free"
        write_status(status)


@app.route("/new_request", methods=["POST"])
def new_request():
    incoming_data = request.get_json(silent=True)
    if incoming_data is None:
        return jsonify(error="Request body must be JSON"), 400

    arrived = time.perf_counter()
    name, worker, was_queued = acquire_worker()
    queue_wait = time.perf_counter() - arrived

    try:
        response = requests.post(
            f"http://{worker['ip']}:{worker['port']}{WORKER_ENDPOINT}",
            json=incoming_data,
            timeout=WORKER_TIMEOUT,
        )
        body, code = response.json(), response.status_code
    except (requests.RequestException, ValueError) as e:
        body, code = {"error": f"{name} failed: {e}"}, 502
    finally:
        # Always release, even on failure, or the worker would stay busy forever
        release_worker(name)

    return jsonify(
        handled_by=name,
        queued=was_queued,
        queue_wait_ms=round(queue_wait * 1000, 1),
        total_ms=round((time.perf_counter() - arrived) * 1000, 1),
        worker_response=body,
    ), code


@app.get("/status")
def status():
    with lock:
        return jsonify(workers=read_status(), queue_length=len(queue))


reset_status()
