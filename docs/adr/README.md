# Architecture Decision Records

One page per decision that a reviewer might question: what we chose, what we rejected, and why. Numbered in the order they were made; never edited after the fact — a changed mind gets a new ADR that supersedes the old one.

Template:

```
# NNNN — Title
Status: accepted | superseded by NNNN
Date: YYYY-MM-DD
## Context      (the situation and the forces at play, in a few sentences)
## Decision     (what we do)
## Alternatives (each one, and why not)
## Consequences (what becomes easier, what becomes harder, what we must revisit)
```

| # | Decision |
|---|---|
| [0001](0001-ci-identity.md) | CI identity: GitHub OIDC with a read-only plan role and a broad apply role, no stored keys |
| [0002](0002-terraform-state.md) | Terraform state in S3 with native locking, bootstrapped by hand once |
| [0003](0003-apply-behind-approval.md) | Infrastructure applies from CI behind a human-approved environment; bootstrap stays laptop-only; repo public |
| [0004](0004-event-contracts.md) | Event contracts as JSON Schema, versioned by file, additive-only, enforced by a golden-file test; identity rules as code |
| [0005](0005-local-dev-stack.md) | Local dev stack: Compose with protocol-faithful stand-ins (MinIO, DynamoDB Local, KRaft Kafka, Qdrant, Bedrock); Ollama for embeddings |
| [0006](0006-services-shape-and-consumer-policy.md) | Five `uv` projects and one shared library (no workspace); retry → `documents.retry` → `documents.dlq`; consumers idempotent by construction, facts over a status word |
| [0007](0007-nat-instance.md) | Egress through a $3 NAT instance (fck-nat) instead of a $33 NAT gateway; free gateway endpoints for S3 and DynamoDB |
| [0008](0008-one-spot-node-and-how-argo-arrives.md) | One spot t4g.large in a managed node group; cluster API reachable from one `/32` until the tailnet; Argo CD bootstrapped once by hand, then self-managed |
| [0009](0009-node-size-domain-embeddings.md) | One t4g.xlarge spot node for the whole platform; a Route 53 domain (zone read, not created); `all-minilm` on Ollama in the cluster as locally; Ollama image kept |
