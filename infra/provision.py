"""Create the key pair, security groups and the three EC2 instances (1 orchestrator, 2 workers)."""

import stat

import boto3

from config import (
    AWS_REGION,
    INSTANCE_PROFILE_NAME,
    INSTANCE_TYPE,
    KEY_NAME,
    KEY_PATH,
    ORCHESTRATOR_PORT,
    ORCHESTRATOR_SG_NAME,
    PROJECT_TAG,
    ROLES,
    ROOT_VOLUME_GB,
    UBUNTU_AMI_NAME,
    UBUNTU_AMI_OWNER,
    WORKER_PORT,
    WORKER_SG_NAME,
)

ec2 = boto3.client("ec2", region_name=AWS_REGION)

ANYWHERE = [{"CidrIp": "0.0.0.0/0"}]


def create_key_pair():
    key = ec2.create_key_pair(KeyName=KEY_NAME)
    KEY_PATH.write_text(key["KeyMaterial"])
    KEY_PATH.chmod(stat.S_IRUSR)  # read-only for the owner: ssh refuses keys other users can read
    print("Saved private key:", KEY_PATH)


def latest_ubuntu_ami():
    images = ec2.describe_images(
        Owners=[UBUNTU_AMI_OWNER],
        Filters=[
            {"Name": "name", "Values": [UBUNTU_AMI_NAME]},
            {"Name": "state", "Values": ["available"]},
        ],
    )["Images"]
    ami = max(images, key=lambda image: image["CreationDate"])
    print("Using AMI:", ami["ImageId"], ami["Name"])
    return ami["ImageId"], ami["RootDeviceName"]


def create_security_groups():
    # Orchestrator: SSH for deployment, HTTP on port 80 for users.
    orchestrator_sg = ec2.create_security_group(
        GroupName=ORCHESTRATOR_SG_NAME,
        Description="SSH and orchestrator HTTP port",
    )["GroupId"]
    ec2.authorize_security_group_ingress(
        GroupId=orchestrator_sg,
        IpPermissions=[
            {"IpProtocol": "tcp", "FromPort": port, "ToPort": port, "IpRanges": ANYWHERE}
            for port in (22, ORCHESTRATOR_PORT)
        ],
    )

    # Workers: SSH for deployment, and port 5000 reachable only from the orchestrator.
    # The SG reference only matches traffic over private IPs, so the orchestrator
    # must call the workers on their private IPs.
    worker_sg = ec2.create_security_group(
        GroupName=WORKER_SG_NAME,
        Description="SSH and worker port from the orchestrator only",
    )["GroupId"]
    ec2.authorize_security_group_ingress(
        GroupId=worker_sg,
        IpPermissions=[
            {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": ANYWHERE},
            {
                "IpProtocol": "tcp",
                "FromPort": WORKER_PORT,
                "ToPort": WORKER_PORT,
                "UserIdGroupPairs": [{"GroupId": orchestrator_sg}],
            },
        ],
    )
    return {"orchestrator": orchestrator_sg, "worker": worker_sg}


def launch_instances(role, count, ami, root_device, sg_id):
    print("Launching", count, INSTANCE_TYPE, "instance(s) for", role)
    response = ec2.run_instances(
        ImageId=ami,
        InstanceType=INSTANCE_TYPE,
        MinCount=count,
        MaxCount=count,
        KeyName=KEY_NAME,
        SecurityGroupIds=[sg_id],
        IamInstanceProfile={"Name": INSTANCE_PROFILE_NAME},
        BlockDeviceMappings=[
            {"DeviceName": root_device, "Ebs": {"VolumeSize": ROOT_VOLUME_GB, "VolumeType": "gp3"}}
        ],
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Project", "Value": PROJECT_TAG},
                    {"Key": "Role", "Value": role},
                    {"Key": "Name", "Value": f"{PROJECT_TAG}-{role}"},
                ],
            }
        ],
    )
    return [instance["InstanceId"] for instance in response["Instances"]]


def provision_instances():
    create_key_pair()
    sg_ids = create_security_groups()
    ami, root_device = latest_ubuntu_ami()

    instance_ids = []
    for role, count in ROLES.items():
        instance_ids += launch_instances(role, count, ami, root_device, sg_ids[role])

    print("Waiting for instances to be running...")

    # Line below is blocking, script stops until instance is running
    ec2.get_waiter("instance_running").wait(InstanceIds=instance_ids)
    return instance_ids


if __name__ == "__main__":
    provision_instances()
