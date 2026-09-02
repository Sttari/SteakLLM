# 0006 — Five `uv` projects and one shared library; retry/dead-letter policy; consumers idempotent by design

Status: accepted
Date: 2026-09-02

## Context

Step 6 turned the event contracts (ADR-0004) into five services — ingest, embedder, summarizer, notifier, gateway — that run as separate containers, scale separately on the cluster, and hold separate IAM identities (Pod Identity, Step 8). Three of them consume the same Kafka topic; every one of them must survive at-least-once delivery, a hard kill, and a rolling restart without losing or duplicating work. The team is one person plus a supervising reviewer; the build must stay understandable at a glance.

## Decision

**Shape: five `uv` projects plus two libraries, one lockfile each, editable path dependencies.** `services/<name>/` follows one template (`services/README.md`); `steakllm-contracts` (schemas, id rules) and `steakllm-common` (settings, JSON logs, consumer loop, clients, probes) are path dependencies with `editable = true` so a library change is live everywhere without re-syncing. Each service builds its own multi-stage, non-root image from the shared `services/` context.

**Retry and dead-letter, as code in `steakllm_common.kafka`.** A handler failure is retried in place three times with backoff (1 s, 4 s, 16 s); still failing, the event is produced *unchanged* to `documents.retry` with `x-attempts`, `x-last-error`, `x-origin-topic` headers and the offset is committed, so one poison message never blocks a partition. The same loop consumes the retry topic; after six attempts in total the event is parked on `documents.dlq`, a queue for humans, and an alert will fire (Step 11). Nothing is dropped silently.

**Idempotent by construction, not by a dedupe table.** Every write is keyed by something derived from the content: `doc_id = sha256(bytes)`, `point_id = uuid5(namespace, "doc:i")`, catalog rows by `doc_id` with never-regress conditional updates. A re-delivered event is an overwrite of the same keys. Where a side effect cannot be overwritten (a notification), the consumer claims the `event_id` in the catalog first and only then acts. Each worker records its own **facts** (`indexed_at`, `chunk_count`, `summarized_at`); the status word is derived, because two consumers of one event finish in either order (Incident 23).

**Amended by chaos drill 1 (6.11).** On SIGTERM the loop finishes the *record* in hand, not the batch, and commits **explicit offsets** for what it handled; the Kafka session timeout is 10 s so a hard kill costs 10 s, not 45 (Incident 24). Ingest refuses to re-announce an object it has already recorded under the same key: duplicates are safe downstream but not free (Incident 25).

## Alternatives

- **One `uv` workspace with a single lockfile.** One `uv lock`, one resolution for everything. Rejected: a dependency bump for the gateway would re-lock and rebuild all five images and re-run all tests, and per-service images from one lockfile need `--package` gymnastics in every Dockerfile. Editable path dependencies give the cross-project editing a workspace is usually chosen for. Revisit if the number of services grows past what five lockfiles can bear.
- **One package with five entry points, one image.** Simplest build. Rejected: one crash domain, one release cadence, one IAM identity for five very different jobs (the gateway is public; the notifier holds SNS rights) and no per-service scaling on the cluster.
- **Retry forever in place.** Rejected: a poison message stalls the partition for every document behind it; the drill's numbers (4 s per document) show how fast a queue builds.
- **No retry, straight to the dead-letter topic.** Rejected: most failures are transient (Ollama restarting, a Bedrock throttle) and cure themselves within the backoff window.
- **A dead-letter topic per service.** Rejected for now: one `documents.dlq` with an `x-origin-topic` header is one place to look; split it when the volume or the on-call handoff demands it.
- **Exactly-once via Kafka transactions.** Rejected: the side effects live in Qdrant, DynamoDB, S3 and SNS, outside any Kafka transaction; "exactly-once" would cover the offsets and nothing that matters.
- **A dedupe table keyed by `event_id` in front of every handler.** Rejected as the default: one extra conditional write per event for a guarantee the natural keys already give; kept only for the notifier, whose side effect has no natural key.

## Consequences

- Any consumer written against the template inherits retry, dead-letter, graceful stop and probes; a new service is a handler function and a `Deps` dataclass.
- Duplicates are a normal event, not an incident; a drill that re-delivers ten documents must show the same point count and the same rows. The chaos-drill script (`tests/chaos/`) is the regression test for this ADR.
- The status word on a catalog row is a convenience for humans; code reads the facts. Anything that "walks a ladder" is a bug by this ADR.
- Cost of the shape: five lockfiles to bump (Dependabot does it), five images of 422–460 MB (open item: slim `common`'s optional clients), five Dockerfiles that must stay identical but for the name (a template test would catch drift; not written yet).
