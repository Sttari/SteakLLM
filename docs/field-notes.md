# Field notes — SteakLLM

Running log of the environment, every incident (cause → fix → lesson), and every measured number. Updated at the end of each session (see the ritual in `PLAN.md`). Opened Aug 28 2026, Step 1.

---

## 1. Setup snapshot

| Thing | Value |
|---|---|
| Project root | `~/Everything/Project/SteakLLM/SteakLLM` |
| Repository | `https://github.com/<owner>/SteakLLM` — private for now; flip public before Step 12 (full-history `gitleaks git` scan first) |
| Default branch | `main` (created with `git init -b main`) |
| Branch protection | `.github/branch-protection.json` — *fill in: applied, or deferred because the repo is private on the free plan* |
| Laptop | macOS, Apple Silicon (no NVIDIA GPU → vLLM never runs locally; Bedrock is the local backend) |
| Tools (from 1.2) | `git` — · `gh` — · `aws` — · `terraform` — · `kubectl` — · `helm` — · `uv` — · `pre-commit` — · `gitleaks` — · `tflint` — · `docker` — *(fill in versions)* |
| AWS | account —, region `us-east-1`, budget alarms — *(Step 2)* |
| Pre-commit hooks | gitleaks · detect-private-key · detect-aws-credentials · large-files · yaml/json · end-of-file · trailing-whitespace · terraform_fmt · ruff · ruff-format |

## 2. Decisions

The decisions on record live in the table at the top of `PLAN.md`; each one becomes an ADR in `docs/adr/` when its step arrives. Add a line here only when a decision changes and why.

| Date | Decision | Why |
|---|---|---|
| Aug 28 2026 | Ollama dropped from local dev; Bedrock is the only local backend, vLLM lands at Step 9 | The Mac can't run vLLM; both backends speak the same OpenAI contract, so services don't change |
| Aug 28 2026 | Repo private until Step 12 | Preference; costs enforceable branch protection on the free plan until then |

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

**(pending) Incident 4 — branch protection on a private repo** (Step 1.11)
*Expected:* `gh api -X PUT …/branches/main/protection` returns 403 on the free plan while the repo is private. *Record what actually happened and the choice made (public now vs. deferred).*

## 4. Measurements

Nothing measured yet. From Step 7: rebuild time (`terraform destroy` → `apply`). From Step 9: GPU summon-to-`/health` time, idle-to-removed time, the load-test table (c=1/8/32). From Step 10: upload-to-searchable and upload-to-email latency, drill results. From Step 11: tokens per GPU-hour and $/Mtok beside Bedrock.

## 5. Lessons (running list)

- Homebrew core is open-source-only; vendor taps exist for a reason.
- Know your repo root before the first `git add`.
- A hook that blocks a commit is doing its job; read what it caught.
- Strings pasted across lines carry invisible characters.
