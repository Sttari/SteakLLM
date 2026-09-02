# services — the five workers and what they share

Five services and two libraries, each a `uv` project in the same mould (see `contracts/`). This page is the template every service follows and the policies they all obey. Written before the code (Step 6.1) and checked against it at the end (6.13); the two places where the drill changed the policy are marked *amended*. The reasoning is ADR-0006.

| Project | Kind | Reads | Writes |
|---|---|---|---|
| `contracts` | library | — | — (the envelope, five event schemas, `doc_id` / `point_id`) |
| `common` | library | — | — (settings, JSON logging, consumer loop, clients, probes) |
| `ingest` | S3-event handler + local runner | S3 `ObjectCreated` / `ObjectRemoved` | catalog `uploaded`; `DocumentUploaded`, `DocumentDeleted` |
| `embedder` | consumer | `documents` | Qdrant points; catalog `indexed`; `DocumentIndexed` |
| `summarizer` | consumer | `documents` | catalog `summarized`; `SummaryReady` (via the gateway's `/v1/chat/completions`) |
| `notifier` | consumer | `documents` | a notification (stdout locally, SNS in the cloud) |
| `gateway` | FastAPI server | HTTP | vLLM / Bedrock, Qdrant, MinIO/S3, catalog; `ChatCompleted` on `chats` |

## The project template

```
services/<name>/
├── pyproject.toml         name steakllm-<name>; requires-python >=3.12; deps + [dependency-groups] dev;
│                          [tool.uv.sources] steakllm-contracts / -common = { path = "../…", editable = true }
├── .python-version        3.12
├── uv.lock                committed
├── Dockerfile             multi-stage: uv build stage → python:3.12-slim runtime, USER app, HEALTHCHECK
├── src/steakllm_<name>/   __init__.py, main.py (entry point), …
└── tests/                 unit (moto, fakes; no stack) and integration (marked; needs `make up`)
```

Entry points are console scripts (`steakllm-embedder`, …) declared in `pyproject.toml`; the Dockerfile's `CMD` runs the same command a developer runs locally. Every service reads its configuration through `steakllm_common.settings` — never `os.environ` directly.

## Policies every service obeys

**Configuration.** From the environment only (the `.env` keys). Typed, validated at start-up; a missing required value fails the process immediately with the key's name in the message. Local-only defaults exist for endpoints (`localhost:…`) and nothing else.

**Logs.** One JSON object per line to stdout, nothing else on stdout. Every line carries `ts`, `level`, `service`, `msg`; while handling an event also `event_id`, `event_type`, `doc_id`, `trace_id`. No secrets, no document text in logs.

```
{"ts":"2026-09-02T20:18:17Z","level":"info","service":"embedder","msg":"indexed","event_id":"…","event_type":"DocumentUploaded","doc_id":"4bc3…","trace_id":"4bf9…","chunk_count":5,"ms":812}
```

**Consumers.** Consumer groups are `steakllm-<service>` — three groups on `documents` means three independent readers, each seeing every event at its own pace. Handlers are idempotent by construction (upsert by `doc_id` / `point_id`; dedupe on `event_id` where a side effect cannot be upserted — the notifier). Offsets are committed for exactly the records that were handled — after the batch, or after the record in hand on a stop — never for what was merely polled (*amended*, Incident 24). Unknown event types are skipped and logged, never failed (a tolerant reader). Ingest, the producer of `DocumentUploaded`, does not announce an object twice under the same key: S3 notifications and the local watcher are both at-least-once, and a duplicate that never enters the log costs no one anything (*amended*, Incident 25).

**Retry and dead-letter.** A handler failure is retried in place up to **3 times** with backoff (1 s, 4 s, 16 s). Still failing → the event is produced unchanged to `documents.retry` with headers `x-attempts`, `x-last-error`, `x-origin-topic`, and the offset is committed (the log keeps moving). A separate retry pass consumes `documents.retry` with the same handler; after **3 more** failures the event goes to `documents.dlq` with the same headers, and an alert fires (Step 11). Nothing is ever dropped silently; the DLQ is a queue for humans.

**Shutdown.** `SIGTERM` → finish the *record* in hand (not the batch: fifty documents at 4 s each would outlive any grace period), commit the offsets of what was handled, close clients — which tells Kafka to reassign the partitions at once — and exit 0, in a few seconds (Compose and Kubernetes both wait 30). `SIGINT` (Ctrl-C locally) does the same. A second signal exits immediately. A hard kill costs the session timeout, 10 s, before the group rebalances (*amended*, chaos drill 1).

**Probes.** Every service serves `GET /healthz` (process alive; 200 always once started) and `GET /readyz` (200 only when its dependencies answer: Kafka metadata, Qdrant, the catalog, …). Consumers run a tiny HTTP server for this on port 8080. Kubernetes' liveness → `/healthz`, readiness → `/readyz`.

**Errors and limits.** Uploads: 20 MB and `application/pdf`, `text/markdown`, `text/plain` only, enforced by ingest (rejected → `rejected/` prefix, `DocumentDeleted` with `quarantine_rejected`). Per-key quotas in the gateway: requests per minute and tokens per day; over → `429` with `Retry-After`.

**Tests.** `uv run pytest` runs unit tests only. Path dependencies on `contracts` and `common` are **editable** (`editable = true` in `[tool.uv.sources]`, in every consumer and in `common` itself), so a change in a shared library is live in every service without re-syncing (field notes, Incident 19). Integration tests are marked `@pytest.mark.integration`, need `make up`, and run with `uv run pytest -m integration`. CI runs both (the stack boots on the runner in Step 6.10).

## The routing policy (the gateway)

Every chat request asks "is vLLM healthy right now?" and routes on the answer; it never waits and never sticks.

1. Probe `VLLM_URL/health` with a 300 ms timeout (cached for 2 s).
2. 200 → forward to vLLM (OpenAI passthrough). Otherwise → Bedrock (Converse, translated to the OpenAI response shape) and bump the demand signal.
3. Circuit breaker: 3 consecutive vLLM failures → **open** for 60 s (Bedrock, no probes); then **half-open**: one probe; success → closed.
4. Every response carries `x-backend: vllm|bedrock`, `x-tokens-in`, `x-tokens-out`.

The summarizer calls the gateway with `model=llm`, so it inherits this policy — it never talks to a backend directly. Locally the stub is always down, so everything answers `x-backend: bedrock`; that is the fallback path being exercised, not a bug.
