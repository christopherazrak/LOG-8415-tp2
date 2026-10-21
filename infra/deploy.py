"""Install Docker on every instance, copy the app code over SSH and start the containers."""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from config import KEY_PATH, ORCHESTRATOR_PORT, REMOTE_DIR, SSH_USER, WORKER_PORT
from instances import get_project_instances

ROOT_DIR = Path(__file__).resolve().parents[1]
SSH_OPTIONS = ["-i", str(KEY_PATH), "-o", "StrictHostKeyChecking=no", "-o", "LogLevel=ERROR"]

# Official Docker docs, "Install using the apt repository" for Ubuntu.
# cloud-init runs apt on first boot, so wait for it to release the apt lock first.
INSTALL_DOCKER = """set -e
cloud-init status --wait > /dev/null
if ! command -v docker > /dev/null; then
  export DEBIAN_FRONTEND=noninteractive
  sudo apt-get update -q
  sudo apt-get install -q -y ca-certificates curl
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt-get update -q
  sudo apt-get install -q -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
"""


def ssh(host, command, stdin=None):
    subprocess.run(["ssh", *SSH_OPTIONS, host, command], input=stdin, text=True, check=True)


def copy_app(host, app_dir):
    ssh(host, f"mkdir -p {REMOTE_DIR}")
    files = [str(path) for path in app_dir.iterdir() if path.is_file()]
    subprocess.run(["scp", *SSH_OPTIONS, *files, f"{host}:{REMOTE_DIR}/"], check=True)


def start_containers(host, health_url):
    # The worker loads the model on startup, so poll its health endpoint before returning
    ssh(
        host,
        f"""set -e
cd {REMOTE_DIR}
sudo docker compose up -d --build
for i in $(seq 60); do curl -sf {health_url} > /dev/null && exit 0; sleep 2; done
echo "Container did not become healthy" >&2; sudo docker compose logs --tail 50; exit 1
""",
    )


def build_status(workers):
    # Private IPs: the worker security group only accepts port 5000 from the orchestrator's SG,
    # which only matches traffic inside the VPC.
    return {
        name: {"ip": worker["private_ip"], "port": str(WORKER_PORT), "status": "free"}
        for name, worker in workers.items()
    }


def deploy_worker(name, worker):
    print(f"[{name}] Deploying on {worker['public_ip']}")
    host = f"{SSH_USER}@{worker['public_ip']}"
    ssh(host, INSTALL_DOCKER)
    copy_app(host, ROOT_DIR / "worker")
    ssh(host, f"echo WORKER_NAME={name} > {REMOTE_DIR}/.env")
    start_containers(host, f"http://localhost:{WORKER_PORT}/health")
    print(f"[{name}] Done")


def deploy_orchestrator(orchestrator, status):
    print(f"[orchestrator] Deploying on {orchestrator['public_ip']}")
    host = f"{SSH_USER}@{orchestrator['public_ip']}"
    ssh(host, INSTALL_DOCKER)
    copy_app(host, ROOT_DIR / "orchestrator")
    ssh(host, f"mkdir -p {REMOTE_DIR}/data && cat > {REMOTE_DIR}/data/status.json", stdin=json.dumps(status, indent=2))
    start_containers(host, f"http://localhost:{ORCHESTRATOR_PORT}/status")
    print("[orchestrator] Done")


def deploy_apps():
    instances = get_project_instances()
    orchestrator = next(i for i in instances if i["role"] == "orchestrator")
    # Sorted so worker1/worker2 names are stable between runs
    worker_list = sorted((i for i in instances if i["role"] == "worker"), key=lambda i: i["instance_id"])
    workers = {f"worker{n}": worker for n, worker in enumerate(worker_list, start=1)}
    status = build_status(workers)

    # The orchestrator doesn't need the workers to be up to start, so deploy all three at once
    with ThreadPoolExecutor(max_workers=len(instances)) as executor:
        futures = [executor.submit(deploy_worker, name, worker) for name, worker in workers.items()]
        futures.append(executor.submit(deploy_orchestrator, orchestrator, status))
        for future in futures:
            future.result()  # re-raises a failed deployment

    url = f"http://{orchestrator['public_ip']}:{ORCHESTRATOR_PORT}"
    print("Orchestrator:", url)
    return url


if __name__ == "__main__":
    deploy_apps()
