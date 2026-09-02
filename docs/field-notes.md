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
| Services (Step 6, in progress) | `common` (settings, logs, loop, clients, text, probes; 32 tests) · `ingest` (10) · `embedder` (8 + 1 integration) · `summarizer` (10 + 1 integration; re-verified through the real gateway at 6.7) · `notifier` (7 + 1) · `gateway` (31 unit + 2 integration with real Bedrock: chat fallback; upload → ingest → index → docs answer → delete) |
| Contracts (Step 4) | `services/contracts` — package `steakllm-contracts` (uv, src layout, Python 3.12): envelope + 5 event schemas (JSON Schema 2020-12), examples, `ids.doc_id`/`ids.point_id`, golden-file compatibility test; 38 tests; `pytest` required in CI |
| Local stack preflight (5.1, Sep 2 2026) | Mac: `arm64`, 16 GB RAM; ports 9092/9000/9001/8000/6333/8080/8081/3000 all free. Docker: CLI only at first (Incident 13) → **OrbStack 2.2.3**: engine 29.4.0, aarch64, 8 CPUs, 7.8 GB for containers, Compose v5.1.2. arm64 images: kafka ✓ minio ✓ dynamodb-local ✓ qdrant ✓ open-webui ✓ nginx ✓; **TEI: amd64 only on every tag** (cpu-1.6/1.7/1.8/latest) — and the cluster's CPU node is Graviton (`t4g`), so this is a cluster problem too, not just a laptop one. Bedrock models visible: `amazon.nova-micro-v1:0` (on-demand), `amazon.nova-lite-v1:0` (on-demand), `anthropic.claude-3-haiku-20240307-v1:0` (on-demand), `anthropic.claude-haiku-4-5-20251001-v1:0` (inference profile) |
| Bedrock (5.6, Sep 2 2026) | model `amazon.nova-micro-v1:0` via the Converse API, region us-east-1, no access request needed (auto-granted); ~$0.035/M input, $0.14/M output tokens. First call: 'ready'. Fallback if summaries disappoint: `anthropic.claude-3-haiku-20240307-v1:0` (~$0.25/$1.25) |
| Local stack images (5.9, all arm64) | `minio/minio:RELEASE.2025-09-07T16-13-09Z` · `minio/mc:RELEASE.2025-08-13T08-35-41Z` · `amazon/dynamodb-local:3.3.1` · `amazon/aws-cli:2.36.37` · `qdrant/qdrant:v1.19.0` · `apache/kafka:4.3.1` · `ollama/ollama:0.33.2` (6.98 GB) · `nginx:1.31.4-alpine` · `ghcr.io/open-webui/open-webui:v0.11.3` (6.47 GB). Engine: OrbStack 2.2.3 |
| Pre-commit hooks | gitleaks · detect-private-key · detect-aws-credentials · large-files · yaml/json · end-of-file · trailing-whitespace · terraform_fmt · ruff · ruff-format |

## 2. Decisions

The decisions on record live in the table at the top of `PLAN.md`; each one becomes an ADR in `docs/adr/` when its step arrives. Add a line here only when a decision changes and why.

| Date | Decision | Why |
|---|---|---|
| Aug 28 2026 | Ollama dropped from local dev; Bedrock is the only local backend, vLLM lands at Step 9 | The Mac can't run vLLM; both backends speak the same OpenAI contract, so services don't change |
| Aug 28 2026 | Repo private until Step 12 | Preference. Branch protection turned out to work on the private repo anyway (see Incident 4) |
| Sep 1 2026 | `release.yml` deferred from Step 3 to Step 6 | A build workflow with nothing to build proves nothing; it lands with the services and Dockerfiles it builds (ADR-0003) |
| Sep 2 2026 | Embedding server is **Ollama**, not TEI; contract = OpenAI `/v1/embeddings` | TEI has no arm64 image on any tag and the cluster's CPU node is Graviton; Ollama is arm64-native on both laptop and cluster. Decided Step 5.1; ADR-0005 |
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

**Incident 13 — no Docker daemon: 1.2's "install Docker Desktop or OrbStack" was ticked but never done** (Sep 2 2026, Step 5.1)
*Symptom:* `docker info` → `failed to connect to the docker API at unix:///var/run/docker.sock`; `docker compose version` → plugin not found. `docker --version` had printed 29.7.2 in 1.2, which satisfied the *Done when* as written.
*Cause:* Homebrew's `docker` *formula* is the command-line client only. A daemon (Docker Desktop, OrbStack, or Colima) is a separate install; nothing in 1.2's check exercised the daemon.
*Fix:* `brew install --cask orbstack` (2.2.3) + first launch. Verified: engine 29.4.0 on aarch64, 8 CPUs, 7.8 GB for containers, Compose v5.1.2, context `orbstack`.
*Lesson:* third ticked-but-not-met box (Incidents 6, 12). "Prints a version" proves a binary exists, not that the thing works — check the *capability* (`docker info`), not the label.

**Incident 14 — DynamoDB Local "healthy" but every request hung: root-owned volume** (Sep 2 2026, Step 5.3)
*Symptom:* `aws dynamodb list-tables` from the Mac → `Read timeout on endpoint URL`; `dynamodb-init` stuck for minutes; Compose reported the service `healthy`.
*Cause:* the image runs as `dynamodblocal` (uid 1000); Docker creates named volumes root-owned (`drwxr-xr-x root`), so SQLite logged `[14] unable to open database file` and the engine hung on every call instead of failing. The healthcheck accepted "any HTTP status" — the JSON front door answered 400 while the engine behind it was dead.
*Fix:* `user: root` on the service (a laptop stand-in; documented in the compose file), and a healthcheck that makes a real `ListTables` call and expects `TableNames` within 2 s. Re-ran the init: `catalog` ACTIVE.
*Lesson:* a healthcheck must exercise the thing you depend on, not the port in front of it. And read the container's own log before the client's error — the cause was on line 10 of `docker compose logs`. Also: the five storage images total 2.1 GB, not the ~600 MB estimated (DynamoDB Local 809 MB, aws-cli 668 MB). Whole stack on disk after 5.7: ~16 GB (Ollama 6.98 GB, Open WebUI 6.47 GB, Kafka 692 MB).

**Incident 15 — the stub answered 503 to the Mac but its own healthcheck said "connection refused"** (Sep 2 2026, Step 5.5)
*Symptom:* `curl -i localhost:8081/health` from the Mac → `503` as designed; Compose marked `vllm-stub` *unhealthy*.
*Cause:* inside the container `localhost` resolves to `::1` (IPv6) and nginx listens on IPv4 only, so the healthcheck's `wget` could not connect. The Mac's request arrives through Docker's published port on IPv4 and never sees the difference.
*Fix:* healthcheck targets `127.0.0.1` explicitly. Verified in-container (exit 0) before recreating.
*Lesson:* an address must be right for where the *caller* lives — the same rule as Kafka's advertised listeners. In healthchecks, write `127.0.0.1`, never `localhost`.

**Incident 16 — `docker compose up --wait` exits 1 because an init container "exited (0)"** (Sep 2 2026, Step 5.7)
*Symptom:* `make up` returned exit 2 after 8 s with Open WebUI still `health: starting`; the raw Compose output ended with `container steakllm-minio-init-1 exited (0)`.
*Cause:* `--wait` treats *any* container that stops as a failure, even a one-shot that finished successfully. It was designed for long-running services; our four init containers are exactly the case it does not handle.
*Fix:* two-phase `make up`: `up -d --wait` on the seven long-running services (nothing depends on the inits, so they don't start), then `up -d` the inits and `docker compose wait` on them, which returns their real exit codes. 17 s to fully healthy; exit 0.
*Lesson:* when a tool's exit code disagrees with what you can see (`ps` said healthy), read the tool's last line before the tool's flag. And measure: "up took 8 s" was the tell — too fast for a 30 s start_period.

**Incident 17 — the whole stack vanished seven seconds after `make up`; `make demo` timed out on Kafka** (Sep 2 2026, Step 6.1)
*Symptom:* `make demo` → `KafkaTimeoutError: Unable to bootstrap from localhost:9092`; `make ps` empty; `docker ps -a` empty.
*Diagnosis:* `docker events --since 60m` showed the four inits exiting 0, then — in one instant seven seconds later — every container killed and destroyed: the fingerprint of a `docker compose down`. Suspected `make up`'s final `docker compose wait`, since Compose 5 has a `--down-project` flag; **reproduced under observation: `make up` leaves 7 containers running with no kill events, and the flag is opt-in.** The teardown came from outside `make up` — most likely a `make down` run in another terminal (it had just been recommended as the way to finish a poking session).
*Fix:* none needed in code; `make up` again. `make ps` is the first command to run when anything "cannot connect".
*Lesson:* `docker events` is the flight recorder — it answers "who stopped this and when" before any guessing. And a hypothesis about your own tooling gets a reproduction before it gets a fix.

**Incident 18 — the embedder turned re-delivered events for a finished document into a retry storm** (Sep 2 2026, Step 6.4)
*Symptom:* the integration test's loop (a fresh consumer group, so it replays the topic) logged `handler failed` three times per historical `DocumentUploaded` of the demo's PDF, parked each on `documents.retry`, and the test timed out before reaching the new document.
*Cause:* the catalog write is conditional on purpose (`uploaded`/`indexed` only, never regress `summarized`), and DynamoDB's refusal (`ConditionalCheckFailedException`) was allowed to propagate as a handler failure. A refusal that means "already further along" is a *successful* outcome under at-least-once delivery, not an error.
*Fix:* catch the conditional-check refusal in the embedder, log `already past indexed; row untouched`, keep the refreshed points (same ids) and the `DocumentIndexed` event. The unit test that had encoded "raises" now asserts "no-op, row untouched". Ingest's write uses `if_not_exists` for the same reason and never had the problem.
*Lesson:* under at-least-once delivery, every consumer must classify *why* a write was refused: "someone got there first" is success; only real faults may retry. And an integration test that replays history is worth its 39 s — the fakes could never have shown this.

**Incident 19 — `'Settings' object has no attribute 'summarizer_max_chars'` in a venv that had the field in source** (Sep 2 2026, Step 6.5)
*Symptom:* the summarizer's tests failed on a field that plainly exists in `services/common/src/…/settings.py`.
*Cause:* `steakllm-common` is a *path* dependency, which `uv` builds into a wheel and installs at sync time — not an editable link. The summarizer had synced before the field was added, so its venv carried the old build. Every service venv synced earlier (ingest, embedder) has the same stale copy.
*Fix (final):* `editable = true` on every path source (`[tool.uv.sources] steakllm-common = { path = "../common", editable = true }`), including inside `common` itself for `contracts` — `uv` refuses two different URLs for one package, so all declarations must agree. Editable installs link the source directory; changes are visible everywhere immediately. (First fix, superseded: `uv sync --reinstall-package …`.)
*Lesson:* a plain path dependency is a built snapshot and `uv` caches the build; in a monorepo of shared libraries, path sources must be editable or the tests test yesterday's library.

**Incident 20 — the gateway's `/healthz` answered with a DynamoDB error; the summarizer could not resolve `gateway`** (Sep 2 2026, Step 6.7)
*Symptom:* `curl localhost:8000/healthz` → `MissingAuthenticationToken … valid AWS access key`; the summarizer, pointed at `GATEWAY_URL`, failed with `nodename nor servname provided`.
*Cause:* two of my own configuration choices colliding. (1) Compose published DynamoDB Local on the Mac's port 8000 — the same port the gateway binds — so `localhost:8000` was DynamoDB, not the gateway. (2) `GATEWAY_URL=http://gateway:8000/v1` is the *container-network* address (for Open WebUI); a process on the Mac cannot resolve `gateway`.
*Fix:* DynamoDB Local published on 8001 (`DYNAMODB_ENDPOINT_URL`); `GATEWAY_URL` is the host address (`localhost:8000`) and Open WebUI gets `OPEN_WEBUI_GATEWAY_URL=http://gateway:8000/v1`; 6.9's Compose service overrides `GATEWAY_URL` for the summarizer container. Gateway `/readyz` now asks the broker for the `chats` topic's metadata instead of `bootstrap_connected()`, which stays false until the first send.
*Lesson:* one `.env` serves two networks — the Mac and the Compose network — and every URL in it belongs to exactly one of them; name them accordingly. And a port list in a plan is a promise to check, not a decoration: 5.1's preflight checked the ports were free, not that they were distinct from each other.

**Incident 21 — four of five service containers exited: `ProfileNotFound: default`; the ingest watcher was "unhealthy"** (Sep 2 2026, Step 6.9)
*Symptom:* embedder, ingest, summarizer, notifier `Exited (1)` seconds after start; ingest, once fixed, stayed `unhealthy`.
*Cause:* (1) the env file hands every container `AWS_PROFILE=default`, and botocore resolves the profile even for clients given explicit MinIO/DynamoDB-Local credentials — only the gateway mounted `~/.aws`. (2) `steakllm-ingest watch` never started the probe server; only the consumer loops did, so its `HEALTHCHECK` had nothing to ask.
*Fix:* mount `~/.aws` read-only into all five (one profile serves the laptop; in the cluster each pod wears its own IAM role); the watcher starts `start_probe_server` like everyone else. Also: the first two image builds failed on `Readme file does not exist` — `.dockerignore` had excluded `README.md`, and the Dockerfiles didn't copy the service's own README that `pyproject.toml` declares.
*Lesson:* a build context is a whitelist you wrote; when a wheel build says a file is missing, it is missing *from the context*, not from the repo. And every long-running process serves the probes, runners included.

**Incident 22 — "Open WebUI shows no models" was my curl being told 401** (Sep 2 2026, Step 6.9)
*Symptom:* `curl localhost:3000/api/models` → `[]`; I concluded the UI wasn't talking to the gateway, restarted it, forced it to re-read its config.
*Cause:* `WEBUI_AUTH=false` removes the login *page*; API calls still need the session token a browser obtains automatically. My parser turned the 401 error body into an empty list. The UI's own log had `GET /api/models 401` all along.
*Fix:* sign in the way the frontend does (`POST /api/v1/auths/signin` works in no-auth mode), then the models are `llm`, `docs`, and a chat through the UI's proxy reached the gateway and Bedrock ("ready"). The `RESET_CONFIG_ON_START` flag added during the hunt stays (dev-only, harmless, documented).
*Lesson:* when a tool "returns nothing", read the *server's* log before theorising — a 401 in the UI's log would have saved three restarts. Parse errors as errors, never as empty results.

**Incident 23 — the first end-to-end run reached "summarized" in 2 s with no chunk count: workers race** (Sep 2 2026, Step 6.10)
*Symptom:* `GET /v1/documents/{id}` said `summarized` almost immediately, `chunk_count` was `None`, and the catalog page showed a document that was summarized but never indexed.
*Cause:* the embedder and the summarizer consume the *same* `DocumentUploaded` in parallel. The summarizer (one Bedrock call) can finish before the embedder (chunking, Ollama, Qdrant). The embedder's write was one conditional statement — "set status to indexed *and* record chunk_count, only if status is uploaded/indexed" — so when the summarizer got there first, the refusal (correct: never regress `summarized`) also threw away the indexing facts. A single status word cannot describe two workers finishing in either order.
*Fix:* the embedder always records its facts (`chunk_count`, `embedding_model`, `indexed_at`) and only the status *word* is conditional; the gateway derives `indexed` and `summarized` from the facts (`stages_of`), not from the word; the catalog page and the status route show each stage as a fact of its own. The e2e test waits for both.
*Lesson:* with independent consumers, "status" is not a ladder — it is a set of facts, each owned by one worker. Model it that way from the start, or the first parallel run will prove it for you. And the end-to-end test found this in its first two seconds; nothing narrower could have.

**Incident 24 — the "graceful" stop of a busy consumer was a SIGKILL in disguise, then 45 s of silence** (Sep 2 2026, Step 6.11)
*Symptom:* chaos drill 1's contrast run (`docker compose stop embedder`, SIGTERM) showed no "stopping after the batch in hand" line, and after the restart the embedder sat idle for ~43 s before indexing anything — the same as after a real SIGKILL.
*Cause:* two mismatches, not a broken handler (an idle SIGTERM exited in under a second). (1) The consumer loop checked the stop flag only after the *whole polled batch*: up to 50 events × ~4 s of Ollama work, while Docker escalates SIGTERM to SIGKILL after 10 s. (2) Kafka keeps a dead member's partitions until its session timeout expires; the default our client negotiated was 45 s, so the restarted member joined and waited.
*Fix:* the loop stops after the *record* in hand and commits **explicit offsets** for what it handled (a bare `commit()` would have committed the whole polled batch, including the unhandled tail — silent loss); `session_timeout_ms=10_000` with 3 s heartbeats; `stop_grace_period: 30s` on the four consumers in Compose (Kubernetes' default is 30 s too). Coordinator log after the fix: the member leaves the group the instant it closes; the restart is stable in 4 s; a hard kill costs 10 s, not 45. Write-up: `docs/chaos/01-embedder-kill.md`.
*Lesson:* "handles SIGTERM" means nothing until you measure *how long* the handler needs against the grace period you actually get. And when a consumer stops early, commit what you handled, never what you polled.

**Incident 25 — restarting ingest re-announced the whole bucket; the drill's first document waited 42 s** (Sep 2 2026, Step 6.11)
*Symptom:* in the contrast run the first drill document was indexed 42 s after upload, before any signal was sent; the embedder log showed thirteen unrelated documents being re-indexed right after the four consumers were recreated.
*Cause:* the local watcher's "already seen" set lives in process memory, so a restart re-lists `quarantine/` and the ingest handler produced a fresh `DocumentUploaded` for every leftover from earlier runs (drill run 1 failed before its cleanup). By the 6.3 contract re-delivery *was* re-announced ("consumers are idempotent") — correct for safety, but each restart cost a full pass of the bucket through the embedder and the summarizer (LLM tokens).
*Fix:* in the handler, not the watcher, because real S3 notifications are at-least-once as well: the catalog update returns the old row (`ReturnValues="ALL_OLD"`); same key already recorded → log "already recorded for this key; not re-announced" and produce nothing. Same bytes under a *new* key still re-announce (the row's key moves). Verified: an ingest restart logged thirteen "already recorded" lines and the embedder did no work.
*Lesson:* idempotent consumers make duplicates *safe*, not *free*. Stop the duplicate at the producer when the producer can tell — and a drill's timeline shows costs a passing test hides.

**Open item — service images are 422–460 MB, above the 400 MB target** (Sep 2 2026, Step 6.9)
`common` pulls boto3, qdrant-client (gRPC + numpy) and pypdf into every image. Levers: optional extras in `common` per client (`steakllm-common[qdrant]`), or `qdrant-client` without gRPC. Decide before Step 8 (pull time on the node); the target stays 400 MB.

**Open item — Nova Micro does not reliably reproduce `[doc:chunk]` citation labels** (Sep 2 2026, Step 6.8)
The `docs` model's system prompt asks for `[doc:chunk]` citations; retrieval is proven by `x-retrieved-doc-ids` and the answer is correct, but the small model often omits the label. Candidates: a stronger prompt (few-shot), Claude 3 Haiku for `docs`, or post-hoc citation from the retrieved set. Decide in Step 11's evaluation job.

**Open item — Ollama image is 6.98 GB** (Sep 2 2026, Step 5.5)
`ollama/ollama:0.33.2` bundles GPU runtimes we never use on CPU. Fine on the laptop; on the Graviton node (Step 8) a 7 GB pull costs minutes and root-volume space. The `/v1/embeddings` contract makes the server swappable: candidate replacement is a self-built ~400 MB ONNX container serving `BAAI/bge-small-en-v1.5` (arm64 + amd64). Decide at Step 8; record in ADR-0005 as a known trade-off.

**Open item — Dependabot's `uv in /services/*` job fails** (first seen Aug 31 2026; expected resolved Sep 1 2026)
The weekly "Dependabot Updates" run errored on the `uv` ecosystem because `services/*` had no Python manifests. `services/contracts` now has `pyproject.toml` + `uv.lock` (Step 4.2). *Verify on the next Monday run (Sep 7 2026); if it still fails, diagnose and record the fix here.*

## 4. Measurements

Local stack (Step 5, Sep 2 2026): `make up` to fully healthy **17 s** (warm volumes); RAM at rest **~1.5 GB** (Open WebUI 666 MB, Kafka 359 MB, DynamoDB Local 208 MB, the rest < 100 MB each); disk ~16 GB of images. `make demo`: **12 s** first run, **7 s** second; Bedrock (Nova Micro) 0.8 s, 432 in / 95 out tokens ≈ $0.00003; 1,569-char PDF → 5 chunks → 5 × 384-dim vectors; idempotency: run 2 left 5 points / 1 catalog row unchanged while the topic went 3 → 6 events.

End-to-end (6.10, Sep 2 2026): `make e2e` — presigned upload → ingest watcher → embedder + summarizer (containers) → `docs` answer with the document retrieved: **4.3 s** against a 60 s budget (Bedrock 2×, Ollama, Qdrant, DynamoDB Local, Kafka).

Services in Compose (6.9, Sep 2 2026): five images built in 17 s (multi-stage, non-root); sizes gateway 460 MB, others 422 MB; `make up` → **12 healthy + 4 inits**; RAM with everything running **~2.6 GB**; Open WebUI → gateway → Bedrock round trip through the UI proxy: 644 ms.

Chaos drill 1 (6.11, Sep 2 2026): 10 documents, embedder killed with 1 indexed; SIGKILL → 10/10 in **44 s** after restart (10 s session timeout + ~3.75 s per document through Ollama); SIGTERM → stop in **3.6 s** (one record), 10/10 in 34 s with no wait. Before the fix: ~43–45 s of waiting after either signal. Qdrant 50/50 points, offsets at end, 0 parked, every run.

Image scans (6.12, Sep 2 2026, Trivy 0.74.0): `steakllm/gateway:local` — **0 fixable CRITICALs** (the release gate), 5 CRITICALs with no fix in Debian 12.15's base (`libsqlite3-0`, `perl-base` ×3, `zlib1g`; listed, not fatal, `ignore-unfixed`); config scan of the five Dockerfiles: **0 misconfigurations** at HIGH/CRITICAL. Bootstrap plan for the release role: 2 to add, 0 to change; checkov 77 passed / 0 failed.

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
- gitleaks flags a *variable* named `…api_key` next to a value-shaped argument; the one-line `# gitleaks:allow` with a reason is the fix, never a weaker rule.
- One bad test file tripped two independent gates (fmt's formatting, tflint's dead-code rule) — layered checks each catch their own concern.
- Measure the stop, not the signal handler: grace period ≥ one unit of work, and commit only what you handled.
- Idempotent consumers make duplicates safe, not free; stop the duplicate at the producer when it can tell.
- zsh does not word-split a variable holding a command (`$C build …` fails "no such file"); use a shell function. Likewise `${PIPESTATUS[0]}` is bash; zsh spells it `$pipestatus[1]` — write the command's output to a file and read `$?` instead.
