# 0002 — Terraform state in S3 with native locking, bootstrapped once by hand

Status: accepted
Date: 2026-08-28

## Context

Terraform's state file is its memory of what it built; whoever holds it can plan and apply. In the prototype it lived on one laptop, which meant one machine was a single point of failure and the pipeline could never run Terraform. State must be shared between the laptop (bootstrap only) and GitHub Actions, protected from concurrent writes, and recoverable when a bad apply corrupts it.

## Decision

- One S3 bucket, `steakllm-tfstate-<random>`, versioned, encrypted (SSE-S3), public access blocked, `prevent_destroy`, noncurrent versions expired after 90 days.
- S3 **native locking** (`use_lockfile = true`, Terraform ≥ 1.10): the lock is an object next to the state; no DynamoDB table.
- One key per module (`bootstrap/terraform.tfstate`, `network/terraform.tfstate`, …) so modules lock and fail independently.
- `infra/bootstrap` is applied once from the laptop with local state, then migrates its own state into the bucket. It is the only module the laptop ever applies.
- The random suffix keeps the bucket name unique without publishing the account ID in backend blocks.

## Alternatives

- **DynamoDB lock table.** The classic pattern; rejected because native locking made it redundant and it was one more resource to bootstrap.
- **Terraform Cloud / HCP Terraform remote state.** Fine, but a second vendor and login for a solo project; rejected for scope.
- **Local state committed to git.** Rejected outright: state contains resource IDs and sometimes secrets, and git is not a locking mechanism.
- **One state for everything.** Rejected: a lock or a corruption in one module would block all of them, and `plan` runtime grows with state size.

## Consequences

- Any bad apply is recoverable by restoring a previous object version of the state file.
- Every module's `backend.tf` must name the bucket and its own key; the CI plan role needs bucket list/read and `*.tflock` write.
- Bootstrap changes (new CI role, budget threshold) still require a laptop apply; they are rare and documented in `infra/bootstrap/README.md`.
