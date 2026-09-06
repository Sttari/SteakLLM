#!/usr/bin/env bash
# Drill 06 — the broker dies mid-batch. KRaft, one node: the Kafka process is killed (kubectl exec … kill 1,
# the container restarts on the same volume); producers retry, consumers rejoin. Claim: nothing lost,
# nothing doubled; the gap is the broker's restart time.
set -euo pipefail
. "$(dirname "$0")/lib.sh"
KEY=$(key)
D1=$(upload b1); stamp "memo ${D1:0:8} uploaded"
until [ "$(status "$D1")" != "-" ]; do sleep 2; done
stamp "row exists → killing the broker's process now (named: kubectl -n kafka exec steakllm-combined-0 -- kill 1)"
kubectl -n kafka exec steakllm-combined-0 -- kill 1 && stamp "killed"
D2=$(upload b2); stamp "memo ${D2:0:8} uploaded during the outage (the Lambda retries its produce)"
n=0; until kubectl -n kafka get kafka steakllm -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null | grep -q True && [ "$(kubectl -n kafka get pod steakllm-combined-0 -o jsonpath='{.status.containerStatuses[0].ready}')" = "true" ]; do sleep 5; n=$((n+5)); done
stamp "broker Ready again after ≈ $n s (restarts=$(kubectl -n kafka get pod steakllm-combined-0 -o jsonpath='{.status.containerStatuses[0].restartCount}'))"
for d in $D1 $D2; do wait_status "$d" summarized 300 && stamp "${d:0:8} summarized" || stamp "${d:0:8} status=$(status "$d") after 300 s"; done
for d in $D1 $D2; do stamp "${d:0:8}: events=$(events "$d") points=$(points "$d")"; done
echo "pass when both memos end summarized with one event of each type; DLQ: $(aws sqs get-queue-attributes --queue-url "$(aws sqs get-queue-url --queue-name steakllm-ingest-dlq --query QueueUrl --output text)" --attribute-names ApproximateNumberOfMessages --query Attributes.ApproximateNumberOfMessages --output text) parked"
