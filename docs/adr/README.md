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
