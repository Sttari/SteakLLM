#!/usr/bin/env bash
# The summon drill (Step 9.5), named as such: the one hand-scaling of vLLM. A stopwatch runs from the
# scale command to /health 200, printing each stage as it flips: NodeClaim, node Ready, GPU advertised,
# pod phases (weights copy, vLLM start), pod Ready, /health. Then a chat through the gateway must answer
# with x-backend: vllm. The un-summon is `--replicas=0`; the node should be gone consolidateAfter (15 min)
# plus a minute later: `bash tests/chaos/summon_drill.sh down` watches that.
#
# Cost while a node exists: g6.xlarge on-demand ≈ $0.80/h plus its 100 GiB gp3 root ≈ $0.01/h.
set -euo pipefail
NS=steakllm
T0=$(date +%s)
stamp() { printf '%5ds  %s\n' "$(( $(date +%s) - T0 ))" "$*"; }
gpu_nodes() { kubectl get nodes -l steakllm.io/pool=gpu --no-headers 2>/dev/null || true; }

if [ "${1:-up}" = "down" ]; then
  kubectl -n "$NS" scale deploy vllm --replicas=0
  stamp "un-summon: replicas=0"
  until [ -z "$(kubectl -n "$NS" get pods -l app.kubernetes.io/name=vllm --no-headers 2>/dev/null)" ]; do sleep 5; done
  stamp "pod gone; the node is empty — consolidateAfter is 15m"
  until [ -z "$(gpu_nodes)" ]; do sleep 15; done
  stamp "node gone from the cluster"
  until [ -z "$(kubectl get nodeclaims --no-headers 2>/dev/null)" ]; do sleep 10; done
  stamp "nodeclaim gone"
  until [ "$(aws ec2 describe-instances --filters Name=tag-key,Values=karpenter.sh/nodepool Name=instance-state-name,Values=pending,running,shutting-down --query 'length(Reservations[].Instances[])' --output text)" = "0" ]; do sleep 15; done
  stamp "EC2 instance gone (meter off for the GPU)"
  exit 0
fi

kubectl -n "$NS" scale deploy vllm --replicas=1
stamp "summon: replicas=1"

until kubectl get nodeclaims --no-headers 2>/dev/null | grep -q .; do sleep 3; done
stamp "nodeclaim: $(kubectl get nodeclaims --no-headers | awk '{print $1, "type="$2, "capacity="$4, "zone="$3}')"

until gpu_nodes | grep -q ' Ready'; do sleep 5; done
stamp "node Ready: $(gpu_nodes | awk '{print $1}')"

until [ "$(kubectl get nodes -l steakllm.io/pool=gpu -o jsonpath='{.items[0].status.allocatable.nvidia\.com/gpu}' 2>/dev/null)" = "1" ]; do sleep 5; done
stamp "nvidia.com/gpu: 1 advertised (device plugin up)"

# follow the Deployment, not a pod name: a rollout mid-drill replaces the pod (Incident 37's fix did)
last=""
until [ "$(kubectl -n "$NS" get deploy vllm -o jsonpath='{.status.readyReplicas}' 2>/dev/null)" = "1" ]; do
  POD=$(kubectl -n "$NS" get pods -l app.kubernetes.io/name=vllm --no-headers 2>/dev/null | awk '{print $1}' | tail -n 1)
  s=$(kubectl -n "$NS" get pod "$POD" --no-headers 2>/dev/null | awk '{print $3}')
  if [ -n "$s" ] && [ "$s" != "$last" ]; then stamp "pod $POD: $s"; last=$s; fi
  if [ "$s" = "Running" ] && [ -z "${weights_said:-}" ]; then weights_said=1; kubectl -n "$NS" logs "$POD" -c weights 2>/dev/null | tail -n 1 | sed 's/^/         /'; fi
  sleep 5
done
POD=$(kubectl -n "$NS" get pods -l app.kubernetes.io/name=vllm --no-headers | awk '{print $1}' | tail -n 1)
stamp "pod Ready"

kubectl -n "$NS" port-forward svc/vllm 18000:8000 >/dev/null 2>&1 &
PF=$!
sleep 3
until curl -sf -o /dev/null http://localhost:18000/health; do sleep 2; done
stamp "/health 200 on the vllm Service"
curl -s http://localhost:18000/v1/models | python3 -c 'import sys, json; print("         models:", [m["id"] for m in json.load(sys.stdin)["data"]])'
kill $PF 2>/dev/null || true

kubectl -n "$NS" logs "$POD" -c vllm 2>/dev/null | grep -iE 'Uvicorn running|Loading weights took|Graph capturing finished|GPU KV cache size' | sed 's/^/         /' | cut -c1-150
echo
echo "next: a chat through the gateway must answer with x-backend: vllm (the chat command follows), then 'bash tests/chaos/summon_drill.sh down'."
