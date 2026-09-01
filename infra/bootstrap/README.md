# infra/bootstrap

The only Terraform module ever applied from a laptop. It creates what the pipeline cannot create for itself:

- the Terraform **state bucket** (versioned, encrypted, private, S3-native locking);
- the **GitHub OIDC** identity provider and two CI roles, `steakllm-ci-plan` (read-only, any branch or PR) and `steakllm-ci-apply` (`main` or the `production` environment only);
- the account **budget** with alarms at 80% actual, 100% actual and 100% forecast.

First apply uses local state; the module then migrates its own state into the bucket (`backend.tf`, added in Step 2.5). See `PLAN.md` Step 2 for the run-through and `docs/adr/0001-ci-identity.md`, `docs/adr/0002-terraform-state.md` for the reasoning.

<!-- touched in 3.4 to trigger the first plan.yml run; harmless -->
