# 0001 — CI identity: GitHub OIDC with two roles, no stored keys

Status: accepted
Date: 2026-08-28

## Context

The pipeline must read and change AWS resources: plan on every pull request, apply on merge. The prototype leaked an API key into logs once; the lesson was that a long-lived key stored anywhere is a liability waiting for a mistake. GitHub Actions can present a signed OpenID Connect (OIDC) token that names the repository, branch, pull request or environment a job runs from.

## Decision

An OIDC identity provider for `token.actions.githubusercontent.com` and two IAM roles:

- `steakllm-ci-plan`: trusts any subject under `repo:<owner>/SteakLLM:*`; permissions are `ReadOnlyAccess` plus read of the state bucket and put/delete of `*.tflock` objects (plan takes the state lock).
- `steakllm-ci-apply`: trusts only `repo:<owner>/SteakLLM:ref:refs/heads/main` and `repo:<owner>/SteakLLM:environment:production`; permissions are `AdministratorAccess` **for now**.

Role ARNs are stored as GitHub repository *variables*, not secrets, because they are not secret. `gh secret list` must stay empty of AWS material.

## Alternatives

- **Long-lived access keys in GitHub secrets.** Rejected: they never expire on their own, they leak into forks and logs, and rotating them is a manual ritual.
- **One role for both plan and apply.** Rejected: a pull request from any branch could then change infrastructure; splitting read from write is cheap and is the first thing a reviewer asks about.
- **A least-privilege apply policy written up front.** Rejected for now: the exact resource set (VPC, EKS, IAM roles for pods, Lambda, DynamoDB, Budgets, WAF…) is not known until Steps 7–11 are built, and guessing produces a policy that is both too broad in places and constantly failing in others.

## Consequences

- Nothing in GitHub can spend AWS money except a job on `main` or in the `production` environment, which requires a human approval click (Step 3).
- The apply role is broader than it should be. **Revisit in Step 12:** use IAM Access Analyzer's policy generation from CloudTrail activity to replace `AdministratorAccess` with a generated least-privilege policy, and add a permissions boundary. Until then, branch protection and the environment gate are the controls.
- The trust policy names the repository; renaming the repo or moving it to an organisation means updating `github_owner`/`github_repo` and re-applying `infra/bootstrap` from the laptop.
