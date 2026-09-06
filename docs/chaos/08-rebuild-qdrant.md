# Drill 08 — rebuild Qdrant from the log (Step 10.7)

**Claim:** The collection is dropped (named), the embedder's consumer group is rewound to the earliest offset while the embedder is at 0, and the embedder is scaled back: every DocumentUploaded in the log is re-embedded. The point count matches the catalog; the rebuild time is the README's number.

**Script:** `tests/chaos/drill_08_rebuild_qdrant.sh` (helpers in `tests/chaos/lib.sh`).

**Result (Sep 6 2026):** PASS — collection dropped (named), root's and the embedder's self-heal paused for the minute of the reset, the group's three partitions rewound to offset 0, re-embedded in 21 s: 17 points for the 17 live documents (points before the drop: 0, after two earlier attempts had left the collection empty).
