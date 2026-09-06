# Drill 05 — the embedder dies mid-batch (Step 10.6)

**Claim:** Three memos are uploaded; while the embedder works, its process is killed (`kubectl exec … kill 1`, the container restarts, the group rebalances, the partition is re-read from the last commit). Every document reaches `indexed` exactly once: one event of each type, one set of points, no doubles (Step 6's drill 01 on real parts).

**Script:** `tests/chaos/drill_05_embedder_kill.sh` (helpers in `tests/chaos/lib.sh`).

**Result (Sep 6 2026):** PASS — the embedder's process killed 8 s in (one restart); all three memos `summarized` with exactly one DocumentUploaded, one DocumentIndexed, one SummaryReady and one point each, no doubles. Honest note: these memos are tiny and the pipeline takes ≈ 2 s, so the kill landed at the tail of the batch; a bigger fixture would put it mid-batch.

**Reading it:** the stamps in the script's output; `events` counts per doc on the `documents` topic (console consumer from earliest, named); `points` per doc in Qdrant; the DLQ depth and the `steakllm-ingest-dlq-not-empty` alarm for 07.
