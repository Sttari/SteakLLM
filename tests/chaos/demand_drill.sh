#!/usr/bin/env bash
# The demand drill (Step 9.6), named as such. No kubectl scale anywhere: one chat through the gateway is
# the only action. Stopwatch from that chat: KEDA sees the chats topic move (Prometheus, scraped every 30 s,
# polled every 15 s) → ScaledObject ACTIVE → replicas 1 → Karpenter's node → pod Ready; a second chat must
# then carry x-backend: vllm. `down` watches the idle path: ACTIVE False after the 5-minute rate window,
# replicas 0 after cooldownPeriod (900 s), the node gone consolidateAfter (15 m) later.
#
# Cost while a node exists: g6.xlarge on-demand ≈ $0.80/h (g6.2xlarge $0.98, g5.xlarge $1.01 if the menu
# falls through). The key is read into a shell variable from Secrets Manager and never printed.
set -euo pipefail
NS=steakllm
GW=${GW:-http://gateway:8000}
T0=$(date +%s)
stamp() { printf '%5ds  %s\n' "$(( $(date +%s) - T0 ))" "$*" >&2; }  # stderr: stamps survive $(…) captures
so() { kubectl -n "$NS" get scaledobject vllm -o jsonpath="{.status.conditions[?(@.type==\"$1\")].status}" 2>/dev/null; }
replicas() { kubectl -n "$NS" get deploy vllm -o jsonpath='{.spec.replicas}' 2>/dev/null; }
gpu_nodes() { kubectl get nodes -l steakllm.io/pool=gpu --no-headers 2>/dev/null || true; }
chat() {  # $1 = label; prints status, x-backend and the answer's first words
  local h=/tmp/steakllm-demand-h.txt b=/tmp/steakllm-demand-b.json
  curl -s --connect-timeout 10 --max-time 120 -D "$h" -o "$b" "$GW/v1/chat/completions" -H "authorization: Bearer $KEY" -H 'content-type: application/json' \
    -d '{"model":"llm","messages":[{"role":"user","content":"In one sentence: what is a steak?"}],"max_tokens":40,"temperature":0}'
  stamp "$1: $(head -n 1 "$h" | tr -d '\r') · $(grep -i '^x-backend' "$h" | tr -d '\r') · $(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); c=d.get("choices"); print((c[0]["message"]["content"] if c else json.dumps(d))[:70])' "$b")"
  grep -i '^x-backend' "$h" | tr -d '\r' | awk '{print $2}'
}
KEY=$(aws secretsmanager get-secret-value --secret-id steakllm/gateway --query SecretString --output text | python3 -c 'import sys,json; print(json.load(sys.stdin)["api_key"])')

if [ "${1:-up}" = "down" ]; then
  stamp "idle watch: ACTIVE=$(so Active) replicas=$(replicas) gpu nodes=$(gpu_nodes | wc -l | tr -d ' ')"
  until [ "$(so Active)" = "False" ]; do sleep 15; done
  stamp "ScaledObject ACTIVE False (the 5-minute rate window closed)"
  until [ "$(replicas)" = "0" ]; do sleep 15; done
  stamp "replicas 0 (cooldownPeriod elapsed)"
  until [ -z "$(gpu_nodes)" ]; do sleep 15; done
  stamp "node gone from the cluster"
  until [ "$(aws ec2 describe-instances --filters Name=tag-key,Values=karpenter.sh/nodepool Name=instance-state-name,Values=pending,running,shutting-down --query 'length(Reservations[].Instances[])' --output text)" = "0" ]; do sleep 15; done
  stamp "EC2 instance gone (meter off for the GPU)"
  exit 0
fi

stamp "at rest: ACTIVE=$(so Active) replicas=$(replicas) gpu nodes=$(gpu_nodes | wc -l | tr -d ' ')"
first=$(chat "chat 1 (the demand)")
until [ "$(so Active)" = "True" ]; do sleep 5; done
stamp "ScaledObject ACTIVE True"
until [ "$(replicas)" = "1" ]; do sleep 5; done
stamp "replicas 1 (KEDA)"
until kubectl get nodeclaims --no-headers 2>/dev/null | grep -q .; do sleep 3; done
stamp "nodeclaim: $(kubectl get nodeclaims --no-headers | awk '{print $1, "type="$2}')"
until gpu_nodes | grep -q ' Ready'; do sleep 5; done
stamp "node Ready: $(gpu_nodes | awk '{print $1}')"
last=""
until [ "$(kubectl -n "$NS" get deploy vllm -o jsonpath='{.status.readyReplicas}' 2>/dev/null)" = "1" ]; do
  POD=$(kubectl -n "$NS" get pods -l app.kubernetes.io/name=vllm --no-headers 2>/dev/null | awk '{print $1}' | tail -n 1)
  s=$(kubectl -n "$NS" get pod "$POD" --no-headers 2>/dev/null | awk '{print $3}')
  if [ -n "$s" ] && [ "$s" != "$last" ]; then stamp "pod $POD: $s"; last=$s; fi
  sleep 5
done
stamp "pod Ready"
for n in 1 2 3 4; do
  b=$(chat "chat $((n+1)) (after warm-up)")
  [ "$b" = "vllm" ] && break
  sleep 20
done
echo
echo "next: 'bash tests/chaos/demand_drill.sh down' watches the idle path (≈ 5 + 15 + 15 + 6 minutes)."
