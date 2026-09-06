# /// script
# requires-python = ">=3.12"
# dependencies = ["boto3>=1.35"]
# ///
"""Replay every parked doorbell event: receive from the DLQ, invoke the Lambda with the original event,
report. Deleting the parked copies is left to a human (`aws sqs purge-queue`), so a replay can never
destroy evidence. Usage: uv run tests/chaos/replay_dlq.py <queue-url> <function-name>"""

from __future__ import annotations

import json
import sys

import boto3


def main(queue_url: str, function: str) -> int:
    sqs, lam = boto3.client("sqs"), boto3.client("lambda")
    seen: set[str] = set()
    replayed = 0
    while True:
        msgs = sqs.receive_message(
            QueueUrl=queue_url, MaxNumberOfMessages=10, VisibilityTimeout=120
        ).get("Messages", [])
        msgs = [m for m in msgs if m["MessageId"] not in seen]
        if not msgs:
            break
        for m in msgs:
            seen.add(m["MessageId"])
            event = json.loads(m["Body"])
            key = event.get("detail", {}).get("object", {}).get("key", "?")
            r = lam.invoke(FunctionName=function, Payload=json.dumps(event).encode())
            out = json.loads(r["Payload"].read() or b"{}")
            print(f"  replayed {event.get('detail-type')} {key} → {out}")
            replayed += 1
    print(
        f"  {replayed} event(s) replayed; the parked copies stay until a human purges the queue"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
