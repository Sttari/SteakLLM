# infra — AWS from code, one module per concern

Every module has its own state key in the shared bucket and is applied by the pipeline behind the `production` gate, **except `bootstrap`**, the one module applied from the laptop (it creates the bucket and the roles the pipeline needs). Modules are applied in dependency order; `apply.yml`'s matrix is that order.

| Module | State key | Applied by | Depends on | What it makes | Monthly cost |
|---|---|---|---|---|---|
| `bootstrap` | `bootstrap/terraform.tfstate` | the laptop, by hand (ADR-0003) | — | state bucket, GitHub OIDC provider, the plan / apply / release roles, budgets | $0 |
| `ecr` | `ecr/terraform.tfstate` | `apply.yml` | bootstrap | five image repositories, immutable tags, lifecycle rules | ≈ $0.15 |
| `data` | `data/terraform.tfstate` | `apply.yml` | bootstrap | documents bucket (TLS-only, EventBridge on, quarantine lifecycle), DynamoDB catalog (PITR, deletion protection), SNS topic + email subscriber (ADR-0012) | pennies (pay-per-use) |
| `network` | `network/terraform.tfstate` | `apply.yml` | bootstrap | VPC, subnets, IGW, NAT instance + EIP, S3 and DynamoDB endpoints (ADR-0007) | ≈ $7 |
| `pipeline` | `pipeline/terraform.tfstate` | `apply.yml`, after network | network (remote state) | the Kafka door's and the ingest Lambda's security groups (10.3); the EventBridge rule, Lambda, DLQ and role (10.4) | ≈ $0 (the NLB itself is Strimzi's Service: ≈ $0.54/day each while the cluster is up) |
| `eks` | `eks/terraform.tfstate` | `apply.yml` | network (remote state) | the cluster, one spot t4g.xlarge node, six add-ons, access entries (ADR-0008/0009) | ≈ $4.60/day while up |
| `platform` | `platform/terraform.tfstate` | `apply.yml`, after eks | eks (by name, not state) | Secrets Manager slots, Pod Identity roles and associations per tenant | ≈ $1.60 |
| `gpu` | `gpu/terraform.tfstate` | `apply.yml`, after platform | eks (by name) | models bucket, the vLLM image repository, Karpenter's role + interruption queue, mirror/vLLM roles, the nightly reaper (ADR-0011) | ≈ $1.35; the GPU bills only while summoned |

**Gates.** Each matrix job references the `production` environment, so every module is approved separately, in order — one click per module, with that module's plan in the run summary above the click. This is deliberate (recorded in ADR-0003's amendment): a reviewer approves a plan, not a run.

**Removal.** `teardown.yml` removes one module (`eks` or `network`; `bootstrap` is not a choice) behind the same gate, with the name typed twice. The rebuild runbook: `docs/runbooks/cluster-rebuild.md` (measured: 40 minutes from nothing to Argo Synced).

**Read-only checks the plan role can run:** `terraform plan` for any module, from any branch or pull request (`plan.yml` posts one sticky comment per module).
