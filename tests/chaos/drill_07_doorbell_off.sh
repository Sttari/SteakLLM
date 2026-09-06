#!/usr/bin/env bash
# Drill 07 — the doorbell fails during uploads. This account's Lambda limit refuses reserved concurrency 0
# (Incident 34a), so the Lambda is broken on purpose instead: its KAFKA_BOOTSTRAP is pointed at a dead
# address (named), two memos are uploaded, EventBridge and the Lambda retry, both events park in the DLQ
# and the alarm fires; then the address is restored and the queue is replayed (`replay_dlq.py`).
# The parked copies are deleted by a human afterwards (`aws sqs purge-queue`).
set -euo pipefail
. "$(dirname "$0")/lib.sh"
KEY=$(key)
FN=steakllm-ingest
ENV_JSON=$(aws lambda get-function-configuration --function-name $FN --query 'Environment.Variables' --output json)
GOOD=$(echo "$ENV_JSON" | python3 -c 'import sys,json; print(json.load(sys.stdin)["KAFKA_BOOTSTRAP"])')
stamp "breaking the doorbell (named): KAFKA_BOOTSTRAP → 10.255.255.1:9094"
aws lambda update-function-configuration --function-name $FN --environment "$(echo "$ENV_JSON" | python3 -c 'import sys,json; e=json.load(sys.stdin); e["KAFKA_BOOTSTRAP"]="10.255.255.1:9094"; e.pop("KAFKA_BOOTSTRAP_LOOKUP_TAG", None); print(json.dumps({"Variables": e}))')" --query LastUpdateStatus --output text
aws lambda wait function-updated --function-name $FN
D1=$(upload d1); D2=$(upload d2); stamp "two memos uploaded during the outage: ${D1:0:8} ${D2:0:8}"
Q=$(aws sqs get-queue-url --queue-name steakllm-ingest-dlq --query QueueUrl --output text)
BASE=$(aws sqs get-queue-attributes --queue-url "$Q" --attribute-names ApproximateNumberOfMessages --query Attributes.ApproximateNumberOfMessages --output text); stamp "DLQ depth before: $BASE"
n=0; until [ "$(aws sqs get-queue-attributes --queue-url "$Q" --attribute-names ApproximateNumberOfMessages --query Attributes.ApproximateNumberOfMessages --output text)" -ge $((BASE+2)) ] || [ $n -ge 900 ]; do sleep 15; n=$((n+15)); done
stamp "DLQ depth $(aws sqs get-queue-attributes --queue-url "$Q" --attribute-names ApproximateNumberOfMessages --query Attributes.ApproximateNumberOfMessages --output text) after ≈ $n s (Lambda: 60 s timeout × 3 attempts each) · alarm: $(aws cloudwatch describe-alarms --alarm-names steakllm-ingest-dlq-not-empty --query 'MetricAlarms[0].StateValue' --output text)"
stamp "restoring the doorbell"
aws lambda update-function-configuration --function-name $FN --environment "$(echo "$ENV_JSON" | python3 -c 'import sys,json; print(json.dumps({"Variables": json.load(sys.stdin)}))')" --query LastUpdateStatus --output text; aws lambda wait function-updated --function-name $FN
stamp "replaying the DLQ"
uv run --quiet "$(dirname "$0")/replay_dlq.py" "$Q" $FN
for d in $D1 $D2; do wait_status "$d" summarized 300 && stamp "${d:0:8} summarized" || stamp "${d:0:8} status=$(status "$d")"; done
for d in $D1 $D2; do stamp "${d:0:8}: events=$(events "$d")"; done
echo "pass when both memos are summarized once each. Then a human empties the queue: aws sqs purge-queue --queue-url $Q"
