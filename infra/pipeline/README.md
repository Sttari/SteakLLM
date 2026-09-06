# infra/pipeline — the doorbell's AWS side (Steps 10.3–10.4)

State key `pipeline/terraform.tfstate`; applied by `apply.yml` after `network` (it reads the network state for the VPC).

| Resource | Notes |
|---|---|
| SG `steakllm-kafka-door` | the internal NLB of Strimzi's `lambda` listener (9094); ingress only from the Lambda's SG; the AWS Load Balancer Controller adds the backend rule to the cluster SG |
| SG `steakllm-ingest-lambda` | the Lambda ENIs; egress to the door (9094), to the S3 and DynamoDB gateway-endpoint prefix lists (443), and HTTPS out via the NAT for Secrets Manager (the CA), which has no gateway endpoint |
| Lambda `steakllm-ingest` | image `steakllm/ingest:lambda-sha-<7>`, arm64, 512 MB, 60 s, in the private subnets; env: bucket, table, `KAFKA_BOOTSTRAP_LOOKUP_TAG` (the Lambda finds the door's NLB by the controller's tag at start; Incident 47), `KAFKA_SECURITY_PROTOCOL=SSL`, `KAFKA_CA_SECRET_ID=steakllm/kafka-ca`; two async retries then the DLQ |
| EventBridge rule `steakllm-ingest-doorbell` | `Object Created`/`Object Deleted` in the documents bucket under `quarantine/` → the Lambda; retry 2, DLQ |
| SQS `steakllm-ingest-dlq` | 14 days; alarm `ingest-dlq-not-empty` → the notifications topic |
| Secret `steakllm/kafka-ca` | Strimzi's cluster CA (PEM), filled by hand from the cluster (named step) |

The nightly GPU reaper lives in `infra/gpu`, not here (the earlier README line said otherwise).
