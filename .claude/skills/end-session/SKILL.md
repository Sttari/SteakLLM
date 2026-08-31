---
name: end-session
description: Run the end-of-session ritual from PLAN.md — recap, tick boxes, field notes, GPU-at-zero check, commit through a PR, meter off. Use when Thomas says he is done for now.
tools: Read, Grep, Glob, Bash, Edit
---

# /end-session — the ritual, never skipped

1. **Recap** what was learned this session in 3–5 bullets, in plain words Thomas could repeat in an interview.
2. **Tick** every substep in `PLAN.md` whose *Done when* was met this session; tick the Step in `README.md`'s roadmap if a whole Step finished. Do not tick anything unverified.
3. **Field notes.** Append to `docs/field-notes.md`: any incident (§3, cause → fix → lesson), any measured number (§4), any lesson (§5). Update §1 if the environment changed (new bucket, role, cluster, endpoint).
4. **Money.** From Step 7 on: `kubectl get nodes` must show no GPU node and `kubectl get deploy vllm -n <ns>` must show 0 replicas; if not, propose `kubectl scale deploy/vllm --replicas=0` and wait for the go-ahead, then verify with `aws ec2 describe-instances --filters Name=tag:karpenter.sh/nodepool,Values=gpu Name=instance-state-name,Values=running`. Before Step 7: confirm nothing billable was created outside the plan.
5. **Commit** all changes on a branch through a PR (`git switch -c chore/session-<date>`, `git add -A`, check `git status` for anything that must not be committed, `git commit`, `git push -u origin HEAD`, `gh pr create --fill`, `gh pr merge --squash --delete-branch`, `git switch main && git pull`). Never push to `main` directly.
6. **Say it out loud:** "Meter is off" (or exactly what is still running and why), and name the next substep for next time.
