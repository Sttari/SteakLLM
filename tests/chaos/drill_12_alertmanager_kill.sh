#!/usr/bin/env bash
# Drill 12 — Alertmanager dies while an alert is firing (Step 11.8). Claim: after the restart the firing
# alert is still shown (Prometheus re-sends it) and no duplicate notification goes out inside the repeat
# interval (4 h): the SNS publish count does not jump.
set -euo pipefail
. "$(dirname "$0")/lib.sh"
POD=alertmanager-kube-prometheus-stack-alertmanager-0
published() { aws cloudwatch get-metric-statistics --namespace AWS/SNS --metric-name NumberOfMessagesPublished --dimensions Name=TopicName,Value=steakllm-notifications --start-time "$(date -u -v-6H +%Y-%m-%dT%H:%M:%S)" --end-time "$(date -u +%Y-%m-%dT%H:%M:%S)" --period 21600 --statistics Sum --query 'Datapoints[0].Sum' --output text; }
alerts() { kubectl -n monitoring port-forward svc/kube-prometheus-stack-alertmanager 19093:9093 >/dev/null 2>&1 & local pf=$!; sleep 3; curl -s --max-time 10 http://localhost:19093/api/v2/alerts | python3 -c 'import sys,json; print(sorted((a["labels"]["alertname"], a["status"]["state"]) for a in json.load(sys.stdin)))'; kill $pf 2>/dev/null; }
stamp "before: alerts=$(alerts) · SNS published (6 h): $(published)"
stamp "removing alertmanager (named: the Alertmanager resource to 0 replicas, then 1)"
# the alertmanager image has no shell: the operator removes the pod when its Alertmanager resource says 0
# replicas, and brings it back at 1 (Argo's self-heal would restore the 1 too). The same PVC returns.
# Argo's self-heal would revert the patch within seconds (drill 08's lesson): pause it on root and the monitoring app for the minute.
kubectl -n argocd patch application root --type merge -p '{"spec":{"syncPolicy":{"automated":{"selfHeal":false}}}}' >/dev/null
kubectl -n argocd patch application monitoring --type merge -p '{"spec":{"syncPolicy":{"automated":{"selfHeal":false}}}}' >/dev/null
kubectl -n monitoring patch alertmanager kube-prometheus-stack-alertmanager --type merge -p '{"spec":{"replicas":0}}' >/dev/null
n=0; until [ -z "$(kubectl -n monitoring get pod $POD --no-headers 2>/dev/null)" ] || [ $n -ge 120 ]; do sleep 5; n=$((n+5)); done; stamp "pod gone after $n s"
kubectl -n monitoring patch alertmanager kube-prometheus-stack-alertmanager --type merge -p '{"spec":{"replicas":1}}' >/dev/null
kubectl -n argocd patch application monitoring --type merge -p '{"spec":{"syncPolicy":{"automated":{"selfHeal":true}}}}' >/dev/null
kubectl -n argocd patch application root --type merge -p '{"spec":{"syncPolicy":{"automated":{"selfHeal":true}}}}' >/dev/null
n=0; until [ "$(kubectl -n monitoring get pod $POD -o jsonpath='{.status.containerStatuses[?(@.name=="alertmanager")].ready}')" = "true" ] || [ $n -ge 300 ]; do sleep 5; n=$((n+5)); done
stamp "alertmanager ready again after $n s"
sleep 90
stamp "after: alerts=$(alerts) · SNS published (6 h): $(published)"
echo "pass when the same alerts are shown after the restart and the SNS publish count did not increase (no duplicate page within the repeat interval)."
