# 0003 — Infrastructure changes apply from CI, behind a human-approved environment

Status: accepted
Date: 2026-09-01

## Context

From Step 3 on, Terraform runs in GitHub Actions: `plan.yml` posts the diff on every pull request that touches `infra/`, and `apply.yml` applies on merge to `main`. The question is what stands between a merge and a change in AWS. Branch protection already requires a pull request and five green checks, but a merge can still be a mistake, a Dependabot bump with unexpected consequences, or a plan that read differently than expected. ADR-0001 gave the apply role `AdministratorAccess` for now; whatever gate we choose is the control that makes that acceptable.

## Decision

`apply.yml` runs inside a GitHub Environment named `production` with one required reviewer (the owner) and a deployment branch policy of *protected branches only*. The job pauses before its first step until the reviewer approves; only then is its OIDC token minted, with subject `environment:production`, which is one of the two subjects the apply role trusts. Plan and apply happen in the same job (`plan -out=tfplan` then `apply tfplan`) so what is applied is exactly what was planned against post-merge state. Concurrency per module queues and never cancels an apply. The reviewer approves on the strength of the pull request's plan comment; the job writes its own plan into the run summary as the record of what was applied.

Two corollaries:

- **`infra/bootstrap` is excluded from `apply.yml`** and remains the one module applied from the laptop. It defines the apply role's own trust and permissions; a bad change applied from CI could lock the pipeline out with no CI path back in. The laptop, with the owner's IAM user, is the recovery path and stays out of the blast radius.
- **The repository became public at this step.** Environment protection rules are a paid feature on private repositories under the free plan (field notes, Incident 11). Going public — planned for Step 12 anyway — unlocked the gate at no cost. Pre-flight: full-history secret scan, `budget_email` marked `sensitive`, personal addresses scrubbed from prose.

## Alternatives

- **Auto-apply on merge, no gate.** Rejected: with an admin-scoped apply role, a merge would be a one-click path to any change in the account; the human click is the second key on that lock, and it produces an audit record under *Deployments* for free.
- **Plan and apply from the same pull-request run** (apply when the PR is approved, before merge). Rejected: it applies code that is not yet on `main`, so `main` and AWS can disagree; and the plan role, which every PR can use, would need write access.
- **GitHub Pro for environment rules on a private repo.** Rejected: $4/month for a feature the public repository gets free, on a project meant to be public.
- **Applying bootstrap from CI too, for uniformity.** Rejected: see the first corollary; uniformity is not worth losing the recovery path.

## Consequences

- Every infrastructure change from here on leaves three records: the PR with its plan comment, the approval under Deployments, and the run summary with the applied plan. CloudTrail shows `assumed-role/steakllm-ci-apply` as the actor, never a person.
- The gate adds a click to every infra merge. Acceptable for a solo project; if it becomes friction, narrow the apply role first (ADR-0001's revisit) before loosening the gate.
- `plan.yml` and `apply.yml` must be kept in step (same `TF_VAR_*` inputs, same module matrix minus bootstrap) or a change can plan clean and fail to apply. Adding a module means one line in each.
- The `release.yml` workflow (build and push images, bump Helm values) is deferred to Step 6 with the services it builds; a build workflow with nothing to build proves nothing.

## Amendment (Sep 3 2026, Step 7) — one approval per module, and a gated teardown

`apply.yml` runs its modules as a matrix, one at a time, and each job references the `production` environment; GitHub therefore asks for an approval **per module**, each with that module's plan in its summary. Discovered in 7.2 (the second module sat at its own gate after the first click), considered as a nuisance, kept as a feature: a reviewer approves a plan, never a run. The alternative — one job looping over the modules behind one click — would apply `eks` on the strength of having read `network`. Cost: three clicks per full apply; a loop of `pending_deployments` calls makes it painless. `teardown.yml` (7.6) reuses the same gate and the same concurrency lock for removals, with the module name typed twice; `bootstrap` is not an option it offers.
