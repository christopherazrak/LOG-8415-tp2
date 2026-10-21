"""Send concurrent test requests to the orchestrator, print the responses and save them in results/."""

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import requests

from config import ORCHESTRATOR_PORT
from instances import get_project_instances

RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"

# More requests than workers, so some of them have to wait in the queue
TEXTS = [
    "I love how easy Docker makes deployments.",
    "This assignment took forever and nothing worked.",
    "The orchestrator queued my request and it still came back fast.",
    "AWS credits running out is my worst nightmare.",
    "Flask is a simple and pleasant framework.",
    "The instance crashed again, this is terrible.",
    "Containers behave the same everywhere, which is great.",
    "I am not sure how I feel about YAML.",
]


def send(url, text):
    start = time.perf_counter()
    response = requests.post(f"{url}/new_request", json={"text": text}, timeout=300)
    return {
        "status_code": response.status_code,
        "client_ms": round((time.perf_counter() - start) * 1000, 1),
        "response": response.json(),
    }


def send_requests(url):
    print(f"Sending {len(TEXTS)} concurrent requests to {url}/new_request")
    with ThreadPoolExecutor(max_workers=len(TEXTS)) as executor:
        results = list(executor.map(lambda text: send(url, text), TEXTS))

    for result in results:
        body = result["response"]
        worker = body.get("worker_response", {})
        print(
            f"{result['status_code']} {body.get('handled_by', '?'):8} "
            f"queued={str(body.get('queued')):5} wait={body.get('queue_wait_ms', 0):7}ms "
            f"{worker.get('label', worker.get('error', '?')):8} {worker.get('input', '')}"
        )

    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"responses-{datetime.now():%Y-%m-%d-%H%M%S}.json"
    path.write_text(json.dumps(results, indent=2))
    print("Saved responses to", path)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        orchestrator_url = sys.argv[1]
    else:
        orchestrator = next(i for i in get_project_instances() if i["role"] == "orchestrator")
        orchestrator_url = f"http://{orchestrator['public_ip']}:{ORCHESTRATOR_PORT}"
    send_requests(orchestrator_url)
