# Chaos drills — each drill written up: what we broke, what we expected, what happened (Steps 6, 10).

## Step 10 drills

| Drill | Doc | Step | Claim |
|---|---|---|---|
| 05-embedder-kill | `05-embedder-kill.md` | Step 10 | the embedder dies mid-batch: exactly once |
| 06-broker-kill | `06-broker-kill.md` | Step 10 | the broker dies mid-batch: nothing lost or doubled |
| 07-doorbell-off | `07-doorbell-off.md` | Step 10 | the Lambda off during uploads: DLQ, alarm, replay |
| 08-rebuild-qdrant | `08-rebuild-qdrant.md` | Step 10 | rebuild the index from the log |
| 09-delete-path | `09-delete-path.md` | Step 10 | the delete path, end to end, idempotent |
| 10-restore | `10-restore.md` | Step 10 | point-in-time restore of the catalog |
