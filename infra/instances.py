"""List the running project instances; used by the deploy scripts to find IPs by role."""

import boto3

from config import AWS_REGION, PROJECT_TAG

ec2 = boto3.client("ec2", region_name=AWS_REGION)


def get_project_instances():
    response = ec2.describe_instances(
        Filters=[
            {"Name": "tag:Project", "Values": [PROJECT_TAG]},
            {"Name": "instance-state-name", "Values": ["running"]},
        ]
    )
    instances = []
    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            tags = {tag["Key"]: tag["Value"] for tag in instance["Tags"]}
            instances.append(
                {
                    "instance_id": instance["InstanceId"],
                    "role": tags["Role"],
                    "public_ip": instance["PublicIpAddress"],
                    # The orchestrator reaches the workers on this one (see the worker SG)
                    "private_ip": instance["PrivateIpAddress"],
                }
            )
    return instances


def wait_for_ssh_ready():
    # "running" doesn't mean sshd is up yet; status checks passing is a safe signal.
    instance_ids = [instance["instance_id"] for instance in get_project_instances()]
    print("Waiting for instance status checks (SSH readiness)...")
    ec2.get_waiter("instance_status_ok").wait(InstanceIds=instance_ids)


if __name__ == "__main__":
    for instance in get_project_instances():
        print(instance)