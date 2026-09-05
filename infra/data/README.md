# infra/data — documents bucket, DynamoDB catalog, SNS (Step 10.2)

The pipeline's durable state, independent of the cluster (ADR-0012). Applied by `apply.yml` (its own gate), state key `data/terraform.tfstate`.

| Resource | Name | Notes |
|---|---|---|
| S3 bucket | `steakllm-documents-<account>` | public access blocked, versioned, SSE-S3, TLS-only policy, EventBridge notifications on; `quarantine/` expires after 7 days, noncurrent versions after 30 |
| DynamoDB table | `steakllm-catalog` | `pk`/`sk`, on-demand, point-in-time recovery, deletion protection; `doc#…` rows and `watch#…` rows |
| SNS topic | `steakllm-notifications` | one email subscriber from `TF_VAR_NOTIFY_EMAIL` (a GitHub variable, never in git), confirmed by a click |

Cost at rest: pennies (S3 per GB, DynamoDB on-demand per request, SNS per email). Drills 09 and 10 (Step 10.7) exercise the delete path and the point-in-time restore.
