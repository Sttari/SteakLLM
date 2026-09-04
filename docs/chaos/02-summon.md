# Drill 02 — the summon (Step 9.5)

**Claim:** scaling vLLM from 0 to 1 summons one g6.xlarge with no clicks and answers on it within eight minutes; scaling back to 0 removes the node after fifteen empty minutes; nothing survives a forgotten evening (the reaper, 9.7, is the last net).

**Script:** `tests/chaos/summon_drill.sh up` (stopwatch to `/health` 200), then the chat below, then `tests/chaos/summon_drill.sh down` (stopwatch to the instance's disappearance).

**The chat** (the key is read into a shell variable from Secrets Manager, never printed):

```
KEY=$(aws secretsmanager get-secret-value --secret-id steakllm/gateway --query SecretString --output text | python3 -c 'import sys,json; print(json.load(sys.stdin)["api_key"])')
curl -s -D - http://gateway:8000/v1/chat/completions -H "authorization: Bearer $KEY" -H 'content-type: application/json' \
  -d '{"model":"llm","messages":[{"role":"user","content":"In one sentence: what is a steak?"}],"max_tokens":40}'
```

`x-backend: vllm` is the proof; the first request after a summon may still say `bedrock` (the breaker re-probes on the next).

**Results:** docs/field-notes.md §4 (Step 9.5) — summon 17 min 16 s in the clean run, of which 10 min 6 s was an EC2 capacity wait (Incident 41); 7 min 10 s when capacity is there (node Ready in 38 s in runs 1–2, plus 6 min 32 s from node Ready to /health measured in run 3) to `/health`; removal decided at 15 min, instance gone at ≈ 21 min.

**What it found the first time:** Incidents 37–40 (a dropped vLLM flag, Argo's sync resetting replicas, Kubernetes' `VLLM_PORT` service link, the gateway's mode name forwarded as the model).
