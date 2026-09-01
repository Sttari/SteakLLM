# 0004 — Event contracts as JSON Schema, versioned by file, additive-only

Status: accepted
Date: 2026-09-01

## Context

Five services communicate only through events in Kafka (`documents` and `chats` topics) and never call each other. The events are the one agreement between them, written before any service exists, and they must survive years of change: fields added, services rewritten, a consumer in another language. S3 and Kafka both deliver at least once, so the contract must also carry the identity rules that make a duplicate delivery harmless. The question is what form the contract takes and how it may change.

## Decision

- **JSON Schema (draft 2020-12)**, one file per event plus a shared envelope, shipped inside the `steakllm-contracts` Python package so every service validates against the same files. Every field carries a `description`; the schema is the documentation.
- **Versioned by file** (`DocumentUploaded.v1.schema.json`) with the version also in the envelope. **v1 is frozen and additive-only**: optional fields and enum values may be added; nothing is removed, retyped, or tightened. Readers tolerate unknown fields on purpose. A breaking change is a new `v2` file that readers opt into.
- **Enforced mechanically**: `tests/test_compat.py` compares live schemas to a golden fingerprint (`tests/golden/v1.json`) and fails with "create v2" on any breaking change; `pytest` is a required check, so v1 cannot break on `main`.
- **Identity rules as code**: `doc_id = sha256(bytes)`, `point_id = uuid5(fixed namespace, "doc_id:chunk_index")`, with known-answer tests pinning the outputs; every consumer is an upsert keyed on them.

## Alternatives

- **Avro with a Schema Registry (Confluent / Apicurio).** The Kafka-native choice: compact binary, central registry enforcing compatibility rules. Rejected: a registry is one more always-on service on a ~$100/month platform, and binary payloads are not readable with `kcat` in the middle of a chaos drill. The registry's compatibility check is the one thing worth keeping — reproduced here as the golden-file test.
- **Protobuf.** Excellent for RPC and cross-language codegen. Rejected: this stack is JSON-first (Lambda events, FastAPI, DynamoDB items, Bedrock); Protobuf would add a codegen step to every service for no consumer that needs it.
- **Pydantic models as the contract.** Pleasant in Python, and the services will use Pydantic *derived from* these schemas. Rejected as the source of truth: it ties the contract to one language's type system, invisible to a Go consumer, the Lambda console, or a reviewer reading the repo.
- **No versioning; edit in place.** Rejected: with independent consumers reading at their own pace and replaying the log, an in-place change silently breaks whoever is behind.

## Consequences

- Any service, in any language, can validate an event from the schema files alone. The examples in the package are the fixtures for every service's tests.
- Adding a field is a normal PR; removing or retyping one is a `v2` file plus a migration plan. The golden file changes only in its own reviewed commit.
- Readers must treat unknown enum values (e.g. a future `backend`) as "other" rather than fail — the tolerant-reader rule extends to values.
- Pydantic models in the services are generated or hand-written *from* the schemas and tested against the same examples (Step 6); drift between the two is a test failure, not a runtime surprise.
- `point_id`'s namespace and `doc_id`'s hash are part of v1: changing either re-keys every stored vector and document, and is therefore a v2 event with a re-index, never a refactor.
