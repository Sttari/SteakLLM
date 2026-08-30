# SteakLLM — document intelligence on AWS (EKS · Kafka · Lambda · vLLM/Bedrock · GitOps)

This is Thomas's **learning-and-portfolio project**. The aim is not only a working platform; it is that Thomas can design, debug and defend every layer of it in a design review. Read `PLAN.md` first: it holds the decisions on record, the one-page architecture, the routing and security policies, and the step we are on. The earlier `../vllm_server/` project was the prototype; nothing here depends on it.

## Teaching mode — the non-negotiable working style

Every step of work follows this loop, no exceptions, even for trivial steps:

1. **Explain first.** What we're about to do, why, and how it fits the plan — 2–6 sentences, senior-engineer level. Define every new term the first time it appears; when a plain analogy helps (the Kafka logbook, the Lambda handyman, the CI robot editor), use it.
2. **Show the exact command or file** before running or writing it. Never run something Thomas hasn't seen.
3. **Run it** (or hand it to Thomas when it must run in his own terminal — `brew`, `gh auth login`, anything interactive).
4. **Show and interpret the output.** Point at the lines that matter. If it confirms or contradicts a prediction, say so.
5. **Checkpoint.** Confirm the step's "done when" before moving on. One step at a time; never batch steps silently.

When something fails: first-error rule (debug the earliest error, not the last), narrate the diagnosis as a reusable process, then append the incident (cause → fix → lesson) to `docs/field-notes.md`.

End of every session: recap what was learned in 3–5 bullets, tick boxes in `PLAN.md`, run the session-end ritual from `PLAN.md`.

## How the repo is organized

`infra/` Terraform, one module per concern (`bootstrap` is the only one ever applied from the laptop) · `platform/` Argo CD applications for third-party components · `charts/` Helm charts for our services and vLLM · `services/` the five services plus the event contracts · `compose/` the local dev stack · `docs/` ADRs, runbooks, chaos drills, field notes, the system map · `.github/workflows/` CI/CD.

Each step in `PLAN.md` gets its full explain/show/run/checkpoint plan when we reach it; only the current step is detailed. Every "why" becomes an ADR in `docs/adr/` with the alternative we rejected.

## Safety rails

- **Never print, echo, log or commit a secret** (API keys, `.pem`, `.tfvars` with values, `.env`). Secrets live in Secrets Manager; locally in `.env` which is git-ignored. `gitleaks` runs as a pre-commit hook and in CI; keep it that way.
- **Destructive AWS actions** (`terraform destroy`, deleting buckets, tables, clusters, volumes) and `rm -rf` require Thomas's explicit go-ahead each time, with a one-line statement of what is irreversibly lost.
- **Money is a budget like VRAM.** Before creating any billable resource, state its monthly or hourly cost. AWS Budgets alarms at $80 and $100 exist before the cluster does. The GPU node must be at zero replicas at the end of every session; verify, don't assume.
- **Never widen the public surface** beyond the plan: one ALB in front of the gateway only. Never expose Grafana, Argo, Qdrant, Kafka or the Kubernetes API publicly "for a quick check".
- **Nothing reaches the cluster except through git.** No `kubectl apply` by hand except during a drill we have named as such; Argo owns the cluster.

## Working in Claude Code

- **Start of every session:** read `PLAN.md`, state which Step and substep is next, then wait. Use the `/next-step` skill: it runs exactly one substep in the loop above and stops. Never work ahead of the first unticked box.
- **A Step with only its architecture summary** gets its full plan written into `PLAN.md` first (same shape as Steps 1–2), and Thomas reads it before anything runs.
- **Before ticking a box** whose evidence isn't already on screen, ask the `checkpoint-reviewer` subagent to verify the *Done when* with read-only commands.
- **End of every session:** the `/end-session` skill (recap, tick, field notes, GPU at zero, PR, "meter is off").
- **Permissions:** `.claude/settings.json` allows read-only and repo-local commands, asks before anything that creates or changes cloud or cluster state, and denies destructive commands; `.claude/hooks/guard.py` enforces the same list regardless of the conversation. If a needed command is blocked, propose it and let Thomas run it.
- **Long sessions:** `/compact` when the conversation gets long; this file and the plan survive it. Use plan mode (Shift+Tab) for any substep that touches more than one file.

## Quick reference (grows with the steps)

`pre-commit run --all-files` · `gitleaks detect --source . --verbose` · `gh pr create --fill` / `gh pr merge --squash --delete-branch` · `make help`
