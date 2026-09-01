# services/contracts — the event contracts

The envelope, the five event schemas, one example per event, the compatibility test, and the idempotency rules. Python package `steakllm-contracts`, installed by every service.

```
uv sync            # install (creates .venv/, writes uv.lock)
uv run pytest      # examples validate, ids are frozen, v1 is compatible
```

## The notes the services pass each other

Services never call each other. They write **events** — facts in the past tense — into Kafka and read the ones they care about. Every event has the same **envelope** (`id`, `type`, `version`, `time`, `doc_id`, `trace_id`, `source`, `data`); `data` is shaped by the event's own schema:

| Event | Written by | Means |
|---|---|---|
| `DocumentUploaded` | ingest | a file is in the bucket and has an identity |
| `DocumentIndexed` | embedder | its chunks are in the vector store; it is searchable |
| `SummaryReady` | summarizer | a summary and tags are in the catalog |
| `DocumentDeleted` | gateway, ingest | the document is gone everywhere |
| `ChatCompleted` | gateway | one chat request finished (the usage record) |

Schemas: `src/steakllm_contracts/schemas/*.v1.schema.json` (JSON Schema 2020-12; every field has a description). Examples: `src/steakllm_contracts/examples/*.json`. Validate with `steakllm_contracts.validate.validate(event)`.

## The three rules that make "twice" harmless

S3 and Kafka both deliver **at least once**: a note can arrive twice, and a worker can crash halfway and start over. We don't try to prevent that; we make it not matter.

1. **Same bytes → same id.** A document's id is the sha256 of its bytes (`ids.doc_id`). Upload the same file twice and it is the same document, not two.
2. **Same chunk → same point.** Chunk *i* of a document always gets the same vector-store id (`ids.point_id(doc_id, i)`, a UUIDv5 in a fixed namespace). Re-embedding overwrites; it never duplicates. Deleting a document is deleting its points by id.
3. **Every consumer is an upsert.** Workers write by key (doc id, point id, event id), never append. Running a step twice leaves the same result as running it once. If a worker cannot be made idempotent, it must dedupe on the envelope `id` before acting.

These are contract v1. Changing the hash or the namespace would re-key every stored document; `tests/test_ids.py` pins the exact outputs so that cannot happen by accident.

## Changing a contract

Version 1 is frozen: fields may be **added** (optional), never removed or retyped. Readers tolerate unknown fields on purpose. A breaking change is a new file, `<Event>.v2.schema.json`, that readers opt into. `tests/test_compat.py` enforces this against `tests/golden/v1.json`.
