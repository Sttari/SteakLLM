# Drill 07 — the doorbell off during uploads (Step 10.6)

**Claim:** This account refuses reserved concurrency 0 (Incident 34a), so the Lambda is broken on purpose (its Kafka address pointed at a dead host, named). Two memos park in the dead-letter queue after the retries, the alarm fires, the address is restored, `tests/chaos/replay_dlq.py` invokes the Lambda with each parked event; a human purges the parked copies afterwards.

**Script:** `tests/chaos/drill_07_doorbell_off.sh` (helpers in `tests/chaos/lib.sh`).

**Result (Sep 6 2026):** PASS — the Lambda's Kafka address pointed at a dead host (named); two uploads parked in the DLQ after 285 s (three 60 s attempts each), the alarm went to ALARM; address restored; `replay_dlq.py` (uv) invoked the Lambda with each parked event: the two memos ended `summarized` exactly once, and a stale duplicate replay produced nothing (the handler's already-recorded guard). The parked copies stay until a human purges the queue.

**Reading it:** the stamps in the script's output; `events` counts per doc on the `documents` topic (console consumer from earliest, named); `points` per doc in Qdrant; the DLQ depth and the `steakllm-ingest-dlq-not-empty` alarm for 07.
