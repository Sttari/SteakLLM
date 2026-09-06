# SteakLLMChatLatencySLOBurn

**Symptom:** Chat p95 above 10 s for the last hour and the last five minutes.

**Look at:**
- the usage & cost dashboard: which backend is slow?
- if vLLM: `kubectl -n steakllm get pods -l app.kubernetes.io/name=vllm`, its log for 'Avg prompt throughput'; the GPU node's `nvidia-smi` via a debug pod
- if Bedrock: the gateway log's `chat completed` latency_ms; AWS Health for Bedrock us-east-1

**Do:** vLLM: scale it away (KEDA pause at 0) and let Bedrock answer; Bedrock: nothing to do but wait — the breaker keeps vLLM in play

**Escalate:** if the fix is not in this page, write the incident in docs/field-notes.md §3 and add what you learned here.
