# infra/pipeline — the doorbell's AWS side (Steps 10.3–10.4)

State key `pipeline/terraform.tfstate`; applied by `apply.yml` after `network` (it reads the network state for the VPC).

| Resource | Notes |
|---|---|
| SG `steakllm-kafka-door` | the internal NLB of Strimzi's `lambda` listener (9094); ingress only from the Lambda's SG; the AWS Load Balancer Controller adds the backend rule to the cluster SG |
| SG `steakllm-ingest-lambda` | the Lambda's ENIs; egress to the door (9094) and to the S3 and DynamoDB gateway-endpoint prefix lists (443) — no NAT, no internet |
| (10.4) EventBridge rule, Lambda `steakllm-ingest`, SQS DLQ, IAM role | to come |

The nightly GPU reaper lives in `infra/gpu`, not here (the earlier README line said otherwise).
