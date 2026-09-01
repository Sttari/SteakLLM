# Field notes — SteakLLM

Running log of the environment, every incident (cause → fix → lesson), and every measured number. Updated at the end of each session (see the ritual in `PLAN.md`). Opened Aug 28 2026, Step 1.

---

## 1. Setup snapshot

| Thing | Value |
|---|---|
| Project root | `~/Everything/Project/SteakLLM/SteakLLM` |
| Repository | `https://github.com/Sttari/SteakLLM` — private for now; flip public before Step 12 (full-history `gitleaks git` scan first) |
| Default branch | `main` (created with `git init -b main`) |
| Branch protection | `.github/branch-protection.json` applied to `main` (verified Aug 28 2026): PR required, 0 approvals, enforced for admins, linear history, no force-push, no deletion, conversations resolved; required status checks named in Step 3 |
| Laptop | macOS, Apple Silicon (no NVIDIA GPU → vLLM never runs locally; Bedrock is the local backend) |
| Tools (from 1.2, verified Aug 28 2026) | `gh` 2.98.0 · `aws` 2.36.8 · `terraform` 1.16.0 · `kubectl` 1.37.0 · `helm` 4.2.4 · `uv` 0.12.7 · `pre-commit` 4.6.2 · `gitleaks` 8.30.1 (hook pinned v8.30.0) · `tflint` 0.64.0 · `docker` 29.7.2 |
| AWS | account `066591056087`, region `us-east-1`, budget `steakllm-monthly` ($100 limit; alarms at 80 % actual, 100 % actual, 100 % forecasted) — created in Step 2 |
| Dependabot | version updates weekly (`.github/dependabot.yml`); alerts + security updates enabled by hand Aug 28 2026 (`gh api -X PUT …/vulnerability-alerts`, `…/automated-security-fixes`) — private repos don't get them by default |
| CI/CD (Step 3) | `ci.yml` — gitleaks · terraform fmt/validate · tflint · checkov · ruff, required on `main` (strict) · `plan.yml` — plan role via OIDC, sticky comment per module on infra PRs · `apply.yml` — `production` environment (owner approves, protected branches only), apply role, per-module queue; bootstrap excluded · `release.yml` deferred to Step 6 |
| Contracts (Step 4) | `services/contracts` — package `steakllm-contracts` (uv, src layout, Python 3.12): envelope + 5 event schemas (JSON Schema 2020-12), examples, `ids.doc_id`/`ids.point_id`, golden-file compatibility test; 38 tests; `pytest` required in CI |
| Pre-commit hooks | gitleaks · detect-private-key · detect-aws-credentials · large-files · yaml/json · end-of-file · trailing-whitespace · terraform_fmt · ruff · ruff-format |

## 2. Decisions

The decisions on record live in the table at the top of `PLAN.md`; each one becomes an ADR in `docs/adr/` when its step arrives. Add a line here only when a decision changes and why.

| Date | Decision | Why |
|---|---|---|
| Aug 28 2026 | Ollama dropped from local dev; Bedrock is the only local backend, vLLM lands at Step 9 | The Mac can't run vLLM; both backends speak the same OpenAI contract, so services don't change |
| Aug 28 2026 | Repo private until Step 12 | Preference. Branch protection turned out to work on the private repo anyway (see Incident 4) |
| Sep 1 2026 | `release.yml` deferred from Step 3 to Step 6 | A build workflow with nothing to build proves nothing; it lands with the services and Dockerfiles it builds (ADR-0003) |
| Sep 1 2026 | **Repo public from Step 3.5** (supersedes the above) | Environment protection rules (the human apply gate) are free only on public repos (Incident 11). Pre-flight: full-history gitleaks clean, `budget_email` marked sensitive, personal addresses scrubbed from prose. Alternatives rejected: GitHub Pro ($4/mo) for a feature the public path gives free; dropping the gate |

## 3. Incident log

**Incident 1 — `brew install … tflint`: "No available formula with the name tflint"** (Aug 28 2026, Step 1.2)
*Cause:* TFLint was removed from Homebrew's main catalog because part of its code is under HashiCorp's BUSL license, which Homebrew core doesn't accept. Homebrew also installs *nothing* when one name in the list is unknown, so the other six tools weren't installed either.
*Fix:* `brew install gh kubectl helm uv pre-commit gitleaks`, then `brew install terraform-linters/tap/tflint`.
*Lesson:* Homebrew core is open-source-licensed software only; vendors with source-available licenses host their own tap (Terraform itself lives in `hashicorp/tap`). Read the whole error before assuming a typo.

**Incident 2 — `git add` printed "adding embedded git repository" for a dozen folders; pre-commit said "No .pre-commit-config.yaml file was found"** (Aug 28 2026, Step 1.4–1.7)
*Cause:* the repository root was a parent of the project folder (`~/Everything/Project`), so `git add` swept in sibling projects that are git repos themselves. Git stores those only as pointers to a commit ("gitlinks"), and clones would get empty folders. The pre-commit hook, installed in that outer repo, looked for its config at the wrong root and refused the commit.
*Fix:* `git rev-parse --show-toplevel` to confirm the wrong root; `git reset` to unstage; delete the accidental `.git` (it had no commits); `git init -b main` inside `SteakLLM/SteakLLM`; `pre-commit install` again.
*Lesson:* check `git rev-parse --show-toplevel` before the first `git add` in any new project. Hooks that fail closed are a feature: the bad commit never happened.

**Incident 3 — `gh repo create … --description "…"`: "GraphQL: Description control characters are not allowed"** (Aug 28 2026, Step 1.10)
*Cause:* a line break came along inside the quoted description when the command was pasted across two lines.
*Fix:* create the repo without `--description`, then `gh repo edit --description "…"` on one line.
*Lesson:* APIs validate strictly; when a pasted command fails on a string, suspect invisible characters first.

**Incident 4 — branch protection on a private repo: expected a 403, got none** (Aug 28 2026, Step 1.11)
*Expected:* `gh api -X PUT …/branches/main/protection` refused on a private repo under the free plan.
*Actual:* accepted; `gh api repos/Sttari/SteakLLM/branches/main/protection` shows every setting from `.github/branch-protection.json` in force, including `enforce_admins`.
*Lesson:* plan limits change; verify with a read call rather than trusting a remembered restriction. Dependabot alerts, on the other hand, *are* still off by default on private repos and had to be switched on.

**Incident 5 — `oidc-smoke` red: "Not authorized to perform sts:AssumeRoleWithWebIdentity"** (Aug 28–30 2026, Step 2.6)
*Symptom:* `configure-aws-credentials` retried "Assuming role with OIDC" a dozen times over 2½ minutes, then failed. Provider, trust policy, repo name and variables all read correctly.
*Diagnosis:* stop reading code, ask AWS what it saw. `aws cloudtrail lookup-events --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRoleWithWebIdentity` showed every attempt's subject as `repo:Sttari@43324946/SteakLLM@1350070618:ref:refs/heads/main` — GitHub's **immutable subject** format (numeric owner and repo IDs after the names; `gh api repos/Sttari/SteakLLM/actions/oidc/customization/sub` reports it as `sub_claim_prefix`). The trust policy only matched `repo:Sttari/SteakLLM:*`, which has no `@`, so nothing matched.
*Fix:* `github_owner_id` / `github_repo_id` variables; both roles trust both forms (`terraform apply`: 0 added, 2 changed). Re-run → `assumed-role/steakllm-ci-plan/GitHubActions`.
*Lesson:* an OIDC refusal is a claim mismatch; CloudTrail shows the claim, the workflow log never does. The ID form is the better trust anchor anyway: names can be re-registered, IDs can't.

**Incident 6 — commits authored as `sttari@mac.home`; checkpoint 1.3 was ticked but not met** (Aug 30 2026, Step 2.7)
*Symptom:* `git commit` printed "Your name and email address were configured automatically based on your username and hostname." The first commit on `main` carries that address too; GitHub can't link it to the account.
*Cause:* `git config --global user.name/user.email` were never set; `gh auth login` authenticates `gh`, it does not configure `git`.
*Fix:* set both globally to the address GitHub already uses on the squash-merges, then `git commit --amend --reset-author --no-edit` on the unpushed commit.
*Lesson:* a ticked box is a claim; the *Done when* is the evidence. Re-verify with the read command (`git config --global user.email`) rather than trusting the tick.

**Incident 7 — first `ci.yml` run: gitleaks 403, checkov 6 findings** (Sep 1 2026, Step 3.2)
*Symptom:* gitleaks job died in 10 s — `Resource not accessible by integration` (403 on `GET /pulls/8/commits`); checkov failed with 6 findings on the bootstrap module.
*Cause:* the workflow's least-privilege `permissions:` block (`contents: read` only) revoked the `pull-requests: read` grant gitleaks-action needs on `pull_request` events. Checkov: one real gap (no abort rule for stale multipart uploads — invisible billable fragments) and five deliberate design decisions that weren't yet on the record anywhere the scanner could see.
*Fix:* `pull-requests: read` added to `ci.yml`; `abort_incomplete_multipart_upload { days_after_initiation = 7 }` in the state bucket lifecycle; five inline `#checkov:skip=<rule>:<reason>` comments (ADR-0001/0002 referenced). Second run: all five jobs green.
*Lesson:* a least-privilege permissions block starts by breaking the tools that need more — the 403's URL names the missing permission. A security scanner's findings split into *fixes* and *decisions*; record the decisions where the scanner reads them, so the report shows the reasoning instead of noise.

**Incident 8 — first `plan.yml` run proposed emptying the budget alarm email** (Sep 1 2026, Step 3.4)
*Symptom:* the sticky plan comment on PR #10 showed `Plan: 0 to add, 1 to change, 0 to destroy` — an in-place update to `aws_budgets_budget.monthly` — instead of the expected "No changes."
*Cause:* the `TF_VAR_BUDGET_EMAIL` repository secret was never created; GitHub expands a missing secret to an **empty string**, a legal value for a string variable, so Terraform happily planned `budget_email = ""` — a change that would have silently killed the cost alarms if merged.
*Fix:* create the secret through the GitHub CLI's interactive prompt (keeps the address out of shell history), and add a `validation` block to `budget_email` (must match `^[^@]+@[^@]+$`) so an unset secret now fails the plan loudly instead of proposing a broken alarm.
*Lesson:* a missing secret does not error — it becomes `""`. Validate variables whose emptiness is meaningful. And this is plan-on-PR working as designed: the bad change sat in a comment for a human to read, not in AWS. (Bonus: the guard hook blocked the first draft of this very entry because the prose contained a guarded command pattern — regex guards can't tell mentions from use; fail-closed is the right default.)

**Incident 9 — the recreated secret was *still* empty: an interactive prompt with no terminal** (Sep 1 2026, Step 3.4)
*Symptom:* after Incident 8's fix, the secret existed in `gh secret list`, yet the re-run plan job showed `TF_VAR_budget_email:` empty in its environment — caught this time by the new validation, with our own error message.
*Cause:* the CLI's interactive secret prompt was run through the session's `!` executor, which attaches no real terminal; the prompt read end-of-file from an empty stdin and stored an **empty string**. "Completed with no output" was the tell.
*Fix:* set the value non-interactively with `--body "$(grep budget_email …/terraform.tfvars | cut -d'"' -f2)"` — pulled straight from the git-ignored tfvars, so the address never appears in the command, history, or output. Job re-run → plan green, sticky comment "No changes."
*Lesson:* existence is not validity — verify a secret took a *value*, not just that it lists. And interactive prompts need a real TTY; in any non-interactive context, pass values explicitly from a guarded source.

**Incident 10 — "Base branch was modified. Review and try the merge again."** (Sep 1 2026, Step 3.4)
*Symptom:* `git push && gh pr merge` failed at the merge with that GraphQL error, though `main` had not moved.
*Cause:* a race of our own making: the chained push moved the PR head a second before the merge call, which had been computed against the pre-push head. GitHub refused rather than merge a stale computation — with strict-mode required checks, the push also re-queued all six checks, blocking the merge until green.
*Fix:* wait for the re-triggered checks, retry the merge alone. Merged clean.
*Lesson:* never chain a push and a merge in one breath; under `strict` status checks, every push re-arms the gate. Push, let CI settle, then merge.

**Incident 11 — environment protection rules refused: "billing plan doesn't support required reviewers"** (Sep 1 2026, Step 3.5)
*Symptom:* `PUT …/environments/production` with `reviewers` + `deployment_branch_policy` → HTTP 422. The environment itself was created, with zero protection rules.
*Cause:* on the free plan, environment *protection rules* are available only for **public** repositories (branch protection, by contrast, worked on the private repo — Incident 4). Plan limits are feature-by-feature; don't generalise from one.
*Fix:* decision recorded in §2 (public now vs Pro vs no gate). Pre-flight for going public: full-history `gitleaks git` scan (13 commits, clean), `budget_email` marked `sensitive`, prose scrubbed of personal addresses.
*Lesson:* check a feature's plan gating with a read call or a throwaway request *before* designing around it; a 422 late in a step costs a decision, not just a retry.

**Incident 12 — the 1.6 skeleton was never created; box ticked on a *Done when* that was never true** (Sep 1 2026, Step 4.1)
*Symptom:* Step 4's preflight found no `services/` at all — nor `platform/`, `charts/`, `compose/`, `Makefile`, `LICENSE`, `.env.example`, `.editorconfig`, `CONTRIBUTING.md`, PR template. The first commit held seven files; none of the skeleton.
*Cause:* 1.6 was ticked from memory, not from `tree -L 2`. Git stores no empty directories, so even folders made by hand without a file inside vanish from history.
*Fix:* created every item 1.6 lists (directories with one-line READMEs, root files, `Makefile` with stub targets) during 4.1; re-verified with `tree`.
*Lesson:* second time this pattern bit (see Incident 6). Before ticking any box, run the *Done when* command and look at its output — a tick is a claim, the output is the evidence. And git will silently drop an empty folder; a README stub is what keeps a room on the map.

**Open item — Dependabot's `uv in /services/*` job fails** (first seen Aug 31 2026; expected resolved Sep 1 2026)
The weekly "Dependabot Updates" run errored on the `uv` ecosystem because `services/*` had no Python manifests. `services/contracts` now has `pyproject.toml` + `uv.lock` (Step 4.2). *Verify on the next Monday run (Sep 7 2026); if it still fails, diagnose and record the fix here.*

## 4. Measurements

First pipeline apply: **2026-09-01T20:18:17Z** — `infra/ecr`, 10 resources, by `assumed-role/steakllm-ci-apply` (CloudTrail), ~5 s of apply after the approval click; run 33554383123. From Step 7: rebuild time (`terraform destroy` → `apply`). From Step 9: GPU summon-to-`/health` time, idle-to-removed time, the load-test table (c=1/8/32). From Step 10: upload-to-searchable and upload-to-email latency, drill results. From Step 11: tokens per GPU-hour and $/Mtok beside Bedrock.

## 5. Lessons (running list)

- Homebrew core is open-source-only; vendor taps exist for a reason.
- Know your repo root before the first `git add`.
- A hook that blocks a commit is doing its job; read what it caught.
- Strings pasted across lines carry invisible characters.
- When STS says "not authorized", read the subject in CloudTrail before touching the policy.
- In zsh, quote any `--query` containing `[0]`; unquoted brackets are globs.
- Every terraform command reads the directory it stands in; a "no resources" surprise usually means wrong cwd.
- Absolute paths in every scripted command: a shell whose working directory persists between commands will happily run `sed` on a file that isn't there.
- Never feed markdown with backticks through an unquoted heredoc: the shell executes the backticks.
- One bad test file tripped two independent gates (fmt's formatting, tflint's dead-code rule) — layered checks each catch their own concern.
