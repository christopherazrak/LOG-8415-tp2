"""Shared config for the boto3 provisioning scripts."""

from pathlib import Path

PROJECT_TAG = "assignment2"

KEY_NAME = f"{PROJECT_TAG}-key"
KEY_PATH = Path(__file__).resolve().parents[1] / f"{KEY_NAME}.pem"
ORCHESTRATOR_SG_NAME = f"{PROJECT_TAG}-orchestrator-sg"
WORKER_SG_NAME = f"{PROJECT_TAG}-worker-sg"

ORCHESTRATOR_PORT = 80
WORKER_PORT = 5000
AWS_REGION = "us-east-1"

INSTANCE_PROFILE_NAME = "LabInstanceProfile"

# Assignment default when Moodle doesn't specify one
INSTANCE_TYPE = "t2.large"

# Latest Ubuntu 24.04 LTS (amd64) published by Canonical, resolved at launch time
# so we don't hardcode an AMI ID that changes every few weeks.
UBUNTU_AMI_OWNER = "099720109477"
UBUNTU_AMI_NAME = "ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"
SSH_USER = "ubuntu"
REMOTE_DIR = f"/home/{SSH_USER}/app"

# The default 8 GB root volume is tight for the PyTorch worker image and its build cache
ROOT_VOLUME_GB = 20

# Role tag -> number of instances. Exactly three instances in total.
ROLES = {
    "orchestrator": 1,
    "worker": 2,
}
