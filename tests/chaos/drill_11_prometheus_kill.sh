#!/usr/bin/env bash
# Drill 11 — Prometheus dies mid-scrape (Step 11.8). Its process is killed (the PVC keeps the data); the
# KEDA trigger, the dashboards and the alert rules must come back whole. Claim: no data lost beyond the
# scrape gap; the ScaledObject stays Ready; time to a healthy target again is the number.
set -euo pipefail
. "$(dirname "$0")/lib.sh"
POD=prometheus-kube-prometheus-stack-prometheus-0
stamp "before: prometheus $(kubectl -n monitoring get pod $POD --no-headers | awk '{print $3, "restarts="$4}') · scaledobject ready=$(kubectl -n $NS get scaledobject vllm -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')"
kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
BEFORE=$(curl -s 'http://localhost:19090/api/v1/query' --data-urlencode 'query=count(up)' | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"]["result"][0]["value"][1])'); kill $PF 2>/dev/null
stamp "targets up before: $BEFORE"
stamp "stopping prometheus (named: POST /-/quit through a port-forward)"
# the prometheus image has no shell: ask the process to quit through its lifecycle API (the operator enables it)
kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PQ=$!; sleep 3; curl -s -X POST http://localhost:19090/-/quit; kill $PQ 2>/dev/null; sleep 5
n=0; until [ "$(kubectl -n monitoring get pod $POD -o jsonpath='{.status.containerStatuses[?(@.name=="prometheus")].ready}')" = "true" ] || [ $n -ge 300 ]; do sleep 5; n=$((n+5)); done
stamp "prometheus ready again after $n s (restarts=$(kubectl -n monitoring get pod $POD -o jsonpath='{.status.containerStatuses[?(@.name=="prometheus")].restartCount}'))"
sleep 45
kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 & PF=$!; sleep 3
AFTER=$(curl -s 'http://localhost:19090/api/v1/query' --data-urlencode 'query=count(up)' | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"]["result"][0]["value"][1])')
OLD=$(curl -s 'http://localhost:19090/api/v1/query' --data-urlencode 'query=count(up offset 30m)' | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print(r[0]["value"][1] if r else "0")'); kill $PF 2>/dev/null
stamp "targets up after: $AFTER (before: $BEFORE) · data from 30 min ago still there: $OLD series"
stamp "scaledobject ready=$(kubectl -n $NS get scaledobject vllm -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}') active=$(kubectl -n $NS get scaledobject vllm -o jsonpath='{.status.conditions[?(@.type=="Active")].status}')"
echo "pass when Prometheus is ready again with the same targets, the hour-old data is still queryable, and the ScaledObject stays Ready."
