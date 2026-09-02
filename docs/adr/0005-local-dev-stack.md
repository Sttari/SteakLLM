# 0005 — Local dev stack: Compose with protocol-faithful stand-ins; Ollama for embeddings

Status: accepted
Date: 2026-09-02

## Context

Five services (Step 6) must be written and tested before a cluster exists (Step 7), and afterwards must stay testable without touching the cluster — Argo owns it, and "nothing reaches the cluster except through git" forbids hand-poking. The Mac has 16 GB of RAM, an ARM CPU and no NVIDIA GPU. The cost posture (~$100/month idle) rules out a second cloud environment for development. The same stack has to boot on a GitHub runner for Step 6's integration tests.

## Decision

A Docker Compose stack (`compose/compose.yaml`, `make up` / `make down`) of **stand-ins that speak the real protocol**: MinIO for S3 (same API; only the endpoint differs), Amazon's DynamoDB Local, a single-node Kafka in KRaft mode (what Strimzi runs), Qdrant and Open WebUI as they will run in the cluster, and **Bedrock itself** as the LLM (decision on record: the Mac cannot run vLLM). A five-line nginx **stub** answers 503 as "vLLM is down" so the gateway's health-check → fallback → circuit-breaker path is exercised locally. Every service has a healthcheck that makes a real call; init containers create the bucket, table and topics idempotently. One `.env` at the repo root serves Compose and the services. `make demo` drives a sample PDF through every component with the calls the services will make, and proves the idempotency rules by running twice.

**Embeddings are served by Ollama, not TEI**, behind the OpenAI-compatible `/v1/embeddings` route. TEI publishes no arm64 image on any tag, and the cluster's always-on node is Graviton (ARM) — so TEI would need emulation on the laptop *and* an amd64 node group in the cluster. The contract is the route, so the server stays swappable.

## Alternatives

- **LocalStack for everything.** One emulator for S3, DynamoDB, Lambda and more. Rejected: it emulates rather than runs (subtle behaviour differences, especially in DynamoDB and eventing), has no real Kafka, and gates the useful parts (EKS, Bedrock) behind a paid tier. MinIO and DynamoDB Local are closer to the real thing for the two services we need.
- **A kind / k3d cluster on the laptop.** Real Kubernetes, real Helm charts. Rejected for now: it spends the RAM and the attention budget on cluster mechanics while the job is writing services; Step 7 builds the real cluster, and Argo — not a laptop — deploys to it. Revisit if chart testing needs it (kind in CI is cheap).
- **Mocking S3 and Kafka inside the tests** (moto, fake producers). Rejected as the *only* layer: fast for unit tests and we will use moto there, but a test that passes against a mock and fails against Kafka's at-least-once delivery or S3's eventual listing is the classic trap. Integration tests run against this stack.
- **TEI under emulation locally, an amd64 node in the cluster.** Rejected: two architectures to operate for one small model; a second node group costs money and complexity. Ollama runs natively on both.
- **A cloud dev instance.** Rejected: ~$120/month if forgotten, a minutes-long deploy loop, and a third environment that follows none of the GitOps rules.

## Consequences

- Development and CI integration tests share one definition of "the platform"; a service that works against `make up` works against the real thing at the protocol level. Differences that remain (IAM, VPC, multi-broker Kafka, real S3 eventing) are exactly what Step 10's drills cover in the cluster.
- Two open items carried forward: the Ollama image is ~7 GB (fine on a laptop; at Step 8 a self-built ~400 MB ONNX embeddings container serving `bge-small` may replace it — the route makes that free), and MinIO is in maintenance mode (its last release is a year old; RustFS or Garage are the successors if it ever breaks).
- The stub's contract — `/health` 503, `/v1/*` 503 — is what the gateway's routing policy is written against; Step 9's real vLLM must satisfy the same routes with 200s.
- `make demo` is not a service and must not grow into one: it is the checklist for Step 6 and the smoke test for the stack, deleted or reduced once the services exist.
- Laptop disk: ~16 GB of images. `make nuke` is the only thing that deletes data volumes, and it says so.
