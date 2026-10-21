# LOG8415E Assignment 2

Containerized Flask workers behind a queueing orchestrator on AWS EC2. Three Ubuntu
`t2.large` instances: one orchestrator (Flask, port 80) and two workers (one Docker
container each, Flask + DistilBERT sentiment analysis, port 5000).

## Architecture

```text
user --POST /new_request--> orchestrator :80 --POST /run_model--> worker1 :5000
                            (status.json + queue)              \-> worker2 :5000
```

1. The orchestrator reads `status.json` and picks a `free` worker, marking it `busy`.
2. If both workers are busy, the request waits in an in-memory FIFO queue.
3. When a worker answers, it is handed straight to the oldest queued request; it is
   only marked `free` again when the queue is empty.

All changes to `status.json` and the queue happen under one lock, so two requests can
never take the same worker. The orchestrator runs as a single gunicorn process with
32 threads so the queue is shared by all requests.

## Repository layout

| Path | Role |
|---|---|
| `worker/` | Worker Flask app, `Dockerfile`, `docker-compose.yml` |
| `orchestrator/` | Orchestrator Flask app, `Dockerfile`, `docker-compose.yml` |
| `infra/config.py` | Region, instance type, ports, names |
| `infra/provision.py` | Creates the key pair, security groups and the 3 instances |
| `infra/instances.py` | Lists the running instances by role (IPs) |
| `infra/deploy.py` | Installs Docker, copies the code, writes `status.json`, starts the containers |
| `infra/send_requests.py` | Sends 8 concurrent test requests and saves the responses in `results/` |
| `infra/run_all.py` | Runs everything end-to-end |
| `infra/teardown.py` | Deletes every AWS resource the project created |

## 1. Setup

Requires Python 3.12+ and [`uv`](https://docs.astral.sh/uv/):

```bash
uv sync
```

Copy the Learner Lab credentials (**AWS Details -> AWS CLI**) into
`~/.aws/credentials`. They expire at the end of each lab session.

## 2. Run everything (single command)

```bash
mkdir -p results
uv run python -u infra/run_all.py 2>&1 | tee "results/run-$(date +%F-%H%M).txt"
```

This provisions the instances, waits until SSH is ready, deploys the three
instances in parallel, then sends the test requests. Expected runtime: about
10-15 minutes, most of it building the worker image (PyTorch + model download).

The steps can also be run one at a time:

```bash
uv run python infra/provision.py
uv run python infra/deploy.py          # after the instances pass their status checks
uv run python infra/send_requests.py   # or: infra/send_requests.py http://<orchestrator-ip>
```

`deploy.py` can be re-run safely to push code changes. `provision.py` cannot: run the
teardown before provisioning again.

## 3. Send a test request

```bash
curl -X POST http://<orchestrator-ip>/new_request \
  -H "Content-Type: application/json" \
  -d '{"text": "I love how easy Docker makes deployments."}'
```

Example response:

```json
{
  "handled_by": "worker1",
  "queued": false,
  "queue_wait_ms": 2.1,
  "total_ms": 85.3,
  "worker_response": {
    "worker": "worker1",
    "model": "distilbert-base-uncased-finetuned-sst-2-english",
    "input": "I love how easy Docker makes deployments.",
    "label": "POSITIVE",
    "score": 0.9993,
    "inference_ms": 61.4
  }
}
```

`GET http://<orchestrator-ip>/status` shows the current `status.json` and queue length.

## 4. Clean up

Stop the instances from the EC2 console when you pause, or delete everything:

```bash
uv run python infra/teardown.py
```

This terminates the instances and deletes the security groups, the key pair and the
local `.pem` file.

## Security

- Orchestrator: ports 22 (SSH) and 80 open.
- Workers: port 22 open; port 5000 accepts traffic **only from the orchestrator's
  security group**. That is why `status.json` holds the workers' private IPs.
- `assignment2-key.pem` is git-ignored; never commit it or AWS credentials.
