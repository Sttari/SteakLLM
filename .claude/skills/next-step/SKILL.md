---
name: next-step
description: Run the next unticked substep of PLAN.md in the explain → show → run → checkpoint loop, one substep only. Use at the start of work and after every checkpoint.
tools: Read, Grep, Glob, Bash, Edit, Write
---

# /next-step — one substep of PLAN.md, the teaching way

You are working under the contract in `CLAUDE.md`. `PLAN.md` is the source of truth; never invent steps that aren't in it.

## Procedure

1. **Locate.** Read `PLAN.md`. Find the first `- [ ]` box in the first Step that still has unticked boxes. State it: "We are on Step N, substep N.M: <title>."

2. **If the Step has only its architecture-level summary (no N.1, N.2… substeps yet):** do not start work. Write the Step's full plan into `PLAN.md`, in the same shape as Steps 1–2: a *Goal* line, a *Concept* paragraph (define every new term, use the project's analogies), then numbered substeps each with the command or file, *Reading it*, and *Done when*, and a final **Step N done when**. Keep the architecture-level summary's decisions; add nothing that contradicts the Decisions table. Then stop and ask Thomas to read it before running anything.

3. **Explain first.** 2–6 sentences: what this substep does, why, how it fits, and any term appearing for the first time. Senior-engineer level, plain words.

4. **Show.** The exact command(s) or the full file content, before running or writing anything. If a file is needed, write it now, show it, and explain each part briefly. Never show a placeholder in angle brackets when a subshell can fill the value (`$(terraform output -raw …)`, `$(aws sts get-caller-identity --query Account --output text)`).

5. **Wait for the go-ahead** if the substep creates, changes or deletes anything outside the repo (AWS resources, cluster objects, GitHub settings) or costs money. State the cost when it isn't zero. Read-only checks and file edits inside the repo may run without asking.

6. **Run** (or hand to Thomas anything interactive: `brew`, `gh auth login`, answering `yes` to a migration).

7. **Interpret.** Point at the lines of output that matter and say what they mean. If the output contradicts the plan's expectation, apply the first-error rule (earliest error, not the last), narrate the diagnosis, and if it was a real incident, append it to `docs/field-notes.md` §3 as cause → fix → lesson.

8. **Checkpoint.** Compare against the substep's *Done when*. If in doubt, ask the `checkpoint-reviewer` subagent to verify with its own read-only commands. Only when met: tick the box in `PLAN.md` (`- [x]`), and if it was the Step's last box, tick the Step in `README.md`'s roadmap too.

9. **Stop.** Summarize in one line what was done and what the next substep is. Do not continue to the next substep without being asked; one substep per invocation.

## Never

- Run anything the guard hook or `CLAUDE.md` safety rails forbid; propose it and stop instead.
- Print, echo or commit a secret; refer to `.env.example` and `*.example.tfvars`.
- Widen the public surface, apply to the cluster by hand, or create billable resources without stating the cost and getting a go-ahead.
- Batch several substeps silently.
