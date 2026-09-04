# Drill 03 — demand (Step 9.6)

**Claim:** one chat through the gateway, and nothing else, summons the GPU: Bedrock answers the first chat, KEDA sees the `chats` topic move, vLLM's replicas go 0 → 1, Karpenter launches the node, and a chat a few minutes later is answered by vLLM. Silence scales it all back to nothing.

**Script:** `tests/chaos/demand_drill.sh up` (the chat, then the stopwatch to `x-backend: vllm`), `tests/chaos/demand_drill.sh down` (the idle path to the instance's disappearance).

**Results:** docs/field-notes.md §4 (Step 9.6). Up: chat answered by Bedrock 3 s, ScaledObject ACTIVE and replicas 1 at 36 s, NodeClaim 37 s, node Ready 81 s, weights and image on the node 6 min 12 s, pod Ready 8 min 52 s, chat answered by vLLM 8 min 53 s. Down: ACTIVE False 4 min 24 s, replicas 0 at 19 min 21 s (cooldown 900 s after ACTIVE False), node gone 39 min 09 s, instance gone 39 min 10 s.

**What to read:** `kubectl -n steakllm get scaledobject vllm` (ACTIVE flips), `kubectl -n keda logs deploy/keda-operator`, then 9.5's chain.
