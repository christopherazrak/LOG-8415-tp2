"""Run the whole assignment end-to-end: provision, deploy, then send test requests."""

from deploy import deploy_apps
from instances import wait_for_ssh_ready
from provision import provision_instances
from send_requests import send_requests

if __name__ == "__main__":
    provision_instances()
    wait_for_ssh_ready()
    orchestrator_url = deploy_apps()
    send_requests(orchestrator_url)
