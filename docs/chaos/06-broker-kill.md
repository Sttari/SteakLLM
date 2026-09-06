# Drill 06 — the broker dies mid-batch (Step 10.6)

**Claim:** One KRaft node; the Kafka process is killed while an upload is in flight. Producers retry, consumers rejoin on the same volume: nothing lost, nothing doubled; the gap is the broker's restart.

**Script:** `tests/chaos/drill_06_broker_kill.sh` (helpers in `tests/chaos/lib.sh`).

**Result (Sep 6 2026):** PASS — the Kafka JVM killed with SIGKILL (pid 1 is tini and ignores signals from inside its namespace); the container restarted once; a memo uploaded during the outage was summarized 8 s later; both memos exactly once with one point each; nothing parked. The readiness stopwatch is coarse (the pod was Ready again within the script's first check).

**Reading it:** the stamps in the script's output; `events` counts per doc on the `documents` topic (console consumer from earliest, named); `points` per doc in Qdrant; the DLQ depth and the `steakllm-ingest-dlq-not-empty` alarm for 07.
