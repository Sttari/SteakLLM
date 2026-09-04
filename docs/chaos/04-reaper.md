# Drill 04 — the reaper (Step 9.7)

**Claim:** a GPU instance that survives the evening — Karpenter dead, the cluster gone, a stuck NodeClaim — is terminated at 03:00 UTC by a Lambda that knows only EC2 tags. And `make cluster-down` never tears eks down while a GPU instance exists.

**Script (by hand, named as a drill):**

1. a chat through the gateway → KEDA summons the node (9.6);
2. `make gpu-check` with the node present → must refuse (exit 1);
3. `kubectl -n steakllm annotate scaledobject vllm autoscaling.keda.sh/paused-replicas=0 --overwrite` → replicas 0, the node empty (the 3 a.m. state);
4. `aws lambda invoke --function-name steakllm-gpu-reaper --log-type Tail /dev/stdout` → the instance id in the reply; `describe-instances` shutting-down; Karpenter's log: NodeClaim removed; no pod comes back;
5. `make gpu-check` → passes; `kubectl -n steakllm annotate scaledobject vllm autoscaling.keda.sh/paused-replicas-` to unpause.

**Result:** one chat (Bedrock) → KEDA ACTIVE 29 s → node Ready 68 s (i-096df6775b94c7e7d); `make gpu-check` with the node present: REFUSING, exit 1; KEDA paused at 0 → replicas 0 and the pod gone at 70 s (the empty node); `aws lambda invoke` at 75 s returned `{"nodepool": "gpu", "instances": ["i-096df6775b94c7e7d"], "count": 1}` in 3.6 s; EC2 shutting-down at 80 s; Karpenter deleted the NodeClaim and the node at 341 s (22:00:36Z), the instance terminated at 342 s; vLLM pods after: 0, replicas 0, no NodeClaim; `make gpu-check` passed at 343 s.

**Cron:** `steakllm-gpu-reaper-nightly`, `cron(0 3 * * ? *)`, ENABLED. Its log group: `/aws/lambda/steakllm-gpu-reaper` (14 days).
