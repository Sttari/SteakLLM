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
| Pre-commit hooks | gitleaks · detect-private-key · detect-aws-credentials · large-files · yaml/json · end-of-file · trailing-whitespace · terraform_fmt · ruff · ruff-format |

## 2. Decisions

The decisions on record live in the table at the top of `PLAN.md`; each one becomes an ADR in `docs/adr/` when its step arrives. Add a line here only when a decision changes and why.

| Date | Decision | Why |
|---|---|---|
| Aug 28 2026 | Ollama dropped from local dev; Bedrock is the only local backend, vLLM lands at Step 9 | The Mac can't run vLLM; both backends speak the same OpenAI contract, so services don't change |
| Aug 28 2026 | Repo private until Step 12 | Preference. Branch protection turned out to work on the private repo anyway (see Incident 4) |

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
*Fix:* set both globally to the address GitHub already uses on the squash-merges (`thomasli9702@outlook.com`), then `git commit --amend --reset-author --no-edit` on the unpushed commit.
*Lesson:* a ticked box is a claim; the *Done when* is the evidence. Re-verify with the read command (`git config --global user.email`) rather than trusting the tick.

## 4. Measurements

Nothing measured yet. From Step 7: rebuild time (`terraform destroy` → `apply`). From Step 9: GPU summon-to-`/health` time, idle-to-removed time, the load-test table (c=1/8/32). From Step 10: upload-to-searchable and upload-to-email latency, drill results. From Step 11: tokens per GPU-hour and $/Mtok beside Bedrock.

## 5. Lessons (running list)

- Homebrew core is open-source-only; vendor taps exist for a reason.
- Know your repo root before the first `git add`.
- A hook that blocks a commit is doing its job; read what it caught.
- Strings pasted across lines carry invisible characters.
- When STS says "not authorized", read the subject in CloudTrail before touching the policy.
- In zsh, quote any `--query` containing `[0]`; unquoted brackets are globs.
