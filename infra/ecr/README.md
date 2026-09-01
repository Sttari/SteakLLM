# infra/ecr

Five ECR repositories, one per service (`gateway`, `embedder`, `summarizer`, `notifier`, `ingest`): scan on push, immutable tags, lifecycle policy (untagged gone after 7 days, last 10 images kept). State key `ecr/terraform.tfstate`.

**Never applied from the laptop.** `plan.yml` posts the plan on the PR; `apply.yml` applies after the `production` approval. First pipeline-managed module (Step 3.7–3.8).
