"""Delete everything the project created: instances, security groups and key pair."""

import stat

import boto3

from config import AWS_REGION, KEY_NAME, KEY_PATH, ORCHESTRATOR_SG_NAME, PROJECT_TAG, WORKER_SG_NAME

ec2 = boto3.client("ec2", region_name=AWS_REGION)


def terminate_instances():
    response = ec2.describe_instances(
        Filters=[
            {"Name": "tag:Project", "Values": [PROJECT_TAG]},
            {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]},
        ]
    )
    instance_ids = [i["InstanceId"] for r in response["Reservations"] for i in r["Instances"]]
    if instance_ids:
        print("Terminating", len(instance_ids), "instance(s)")
        ec2.terminate_instances(InstanceIds=instance_ids)
        ec2.get_waiter("instance_terminated").wait(InstanceIds=instance_ids)


def teardown_all():
    terminate_instances()

    # Security groups can only be deleted once no instance uses them. The worker SG
    # references the orchestrator SG, so it must go first.
    for name in (WORKER_SG_NAME, ORCHESTRATOR_SG_NAME):
        for group in ec2.describe_security_groups(
            Filters=[{"Name": "group-name", "Values": [name]}]
        )["SecurityGroups"]:
            print("Deleting security group:", name)
            ec2.delete_security_group(GroupId=group["GroupId"])

    print("Deleting key pair:", KEY_NAME)
    ec2.delete_key_pair(KeyName=KEY_NAME)
    if KEY_PATH.exists():
        KEY_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)  # make it writable: Windows refuses to delete read-only files
        KEY_PATH.unlink()


if __name__ == "__main__":
    teardown_all()
