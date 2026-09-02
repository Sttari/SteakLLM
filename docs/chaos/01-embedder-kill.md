# Chaos drill 1 — kill the embedder mid-batch (Step 6.11, Sep 2 2026)

**What we broke.** Ten documents uploaded in a burst; while the embedder is in the middle of them,
`docker compose kill embedder` (SIGKILL: no goodbye, no commit), two seconds later `start` it again.
The contrast run does the same with `docker compose stop` (SIGTERM, then SIGKILL after the grace period).
Script: `tests/chaos/drill_01_embedder_kill.py` (`DRILL_SIGNAL=stop` for the contrast; `DRILL_DOCS` for the burst size).

## What we expected (written before the first run)

1. Every document reaches `indexed` after the restart — Kafka re-delivers what was never committed.
2. Qdrant holds exactly `sum(chunk_count)` points for the ten: re-delivery rewrites the *same* point ids
   (`uuid5(namespace, "doc:i")`), so a second pass is an overwrite, never a duplicate.
3. The embedder group's committed offsets reach the end of `documents`.
4. Nothing lands on `documents.retry` or `documents.dlq` because of the kill — a kill is not a handler failure.
5. The SIGTERM contrast stops cleanly: "stopping after the batch in hand" → "consumer closed", exit 0, and
   the restart picks up where it left off with no re-work.

## What happened

| run | signal | first doc indexed | restart → 10/10 | verdict |
|---|---|---|---|---|
| 1 (script bug) | SIGKILL | — | — | script's offset check used an admin API kafka-python does not have; fixed |
| 2, 3 | SIGKILL | ~4 s | ~75 s | **passed** 10/10 · 50/50 points · offsets at end · 0 parked |
| contrast, before the fix | SIGTERM | ~4 s | ~43 s wait, then work | passed, but *no* graceful stop in the log |
| 4, after the fix | SIGKILL | 5.5 s | 44 s (10 s waiting + 34 s work) | **passed** |
| contrast, after the fix | SIGTERM | 5 s | 34 s, no wait; stop took 3.6 s | **passed**, graceful |

Expectations 1–4 held from the first valid run: no duplicates, no loss, nothing parked. Two things did
not match the prediction, and each one changed code:

**Finding A — a hard kill cost ~45 s of silence, and the "graceful" stop was not graceful.**
After SIGKILL the restarted embedder joined the group and then *waited*: Kafka keeps a dead member's
partitions until its *session timeout* expires (the broker's default for our client: 45 s). Worse, the
SIGTERM contrast showed the same 43 s wait and no "stopping after the batch" line — the handler was
never the problem (an idle SIGTERM exits in under a second); the loop finished the *whole polled
batch* before it looked at the stop flag, up to 50 documents × ~4 s, and Docker escalates to SIGKILL
after 10 s. So every rolling restart of a busy consumer would have been a hard kill.
Fixed in `steakllm_common.kafka` (Incident 24): the loop stops after the *record* in hand, commits
**explicit offsets** for what it handled (a bare `commit()` would commit the whole polled batch,
including the records never handled — silent loss), asks Kafka for a 10 s session timeout with 3 s
heartbeats, and Compose gives each consumer `stop_grace_period: 30s`, like Kubernetes' default.
Proof in the coordinator log: at 20:49:29 the member *left* the group the instant it closed ("group is
now empty"), and the restarted member was stable 4 s later. A hard kill now costs 10 s, not 45.

**Finding B — restarting ingest re-announced the whole bucket.**
The contrast run's first document took 42 s to be indexed, before any signal. The embedder was busy
re-indexing thirteen leftovers from earlier runs: the local watcher's "already seen" set lives in
memory, so a restart re-lists `quarantine/` and the handler produced a fresh `DocumentUploaded` for
each. Real S3 notifications are at-least-once too, so the handler — not the watcher — is the right
place to fix it (Incident 25): the catalog write now returns the old row, and "same key, already
recorded" means no second event. Verified: an ingest restart logged thirteen "already recorded for
this key; not re-announced" lines and the embedder did no work.

## What we changed

- `services/common/src/steakllm_common/kafka.py`: stop after the current record; explicit per-partition
  offsets on commit; `session_timeout_ms=10_000`, `heartbeat_interval_ms=3_000`. Unit test: a stop
  after two of five records commits offset 2 and leaves three uncommitted.
- `compose/compose.yaml`: `stop_grace_period: 30s` on the four consumers (the gateway is request/response).
- `services/ingest/src/steakllm_ingest/handler.py`: `ReturnValues="ALL_OLD"`; same key + recorded → skip.
- `docs/field-notes.md`: Incidents 24 and 25; lessons.

## What still costs, and why

A SIGKILL still costs the session timeout (10 s) because a dead process cannot say goodbye; shorter
would make a slow GC pause or a network blip look like a death. `terminationGracePeriodSeconds` on the
cluster must stay above one record's worst case (a PDF through Ollama: a few seconds); 30 s is ample.
The e2e promise ("searchable within 60 s") still holds through a hard kill of one worker only because
the burst is small; Step 10 repeats this drill on the cluster with the real numbers.
