"""The nightly safety net: shut down every GPU-pool instance that is still running.

Karpenter removes an empty GPU node after fifteen idle minutes and nothing should ever survive an
evening — this is the line behind that line. It knows nothing about Kubernetes: it looks for EC2
instances carrying the NodePool's tag and terminates them. Karpenter, if alive, notices the machine is
gone and cleans up its NodeClaim; if the cluster is gone too, nothing is left to clean.
"""

import json
import os

import boto3

NODEPOOL_TAG = "karpenter.sh/nodepool"
NODEPOOL = os.environ.get("GPU_NODEPOOL", "gpu")


def handler(event, context):
    ec2 = boto3.client("ec2")
    resp = ec2.describe_instances(
        Filters=[
            {"Name": f"tag:{NODEPOOL_TAG}", "Values": [NODEPOOL]},
            {
                "Name": "instance-state-name",
                "Values": ["pending", "running", "stopping", "stopped"],
            },
        ]
    )
    ids = [i["InstanceId"] for r in resp["Reservations"] for i in r["Instances"]]
    if ids:
        ec2.terminate_instances(InstanceIds=ids)
    result = {"nodepool": NODEPOOL, "instances": ids, "count": len(ids)}
    print(json.dumps(result))
    return result
