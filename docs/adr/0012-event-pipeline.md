# 0012 — The cloud event pipeline: S3 → EventBridge → a Lambda in the VPC → Kafka through an internal NLB; DynamoDB single table with PITR; a dead-letter queue; SNS by email

Status: proposed (accepted when 10.5's acceptance passes: upload → searchable and an email in under 90 s)
Date: 2026-09-04

## Context

Steps 5–6 built the pipeline against local stand-ins (MinIO, DynamoDB Local, a single-node Kafka, stdout as the notification sink) behind versioned contracts (ADR-0004). Step 10 swaps the real cloud parts in without touching the contracts or the consumers. The one shape problem: the doorbell is a Lambda, which by design lives outside the cluster, and the logbook is Kafka, which lives inside it and speaks cluster DNS. The Lambda must produce to Kafka, so it needs a door.

## Decision

1. **S3 → EventBridge → Lambda, not S3 → Lambda direct.** EventBridge filters (bucket, prefix, created or removed) live in one place, carry retries and a dead-letter queue, and can fan out later (Step 11's tracing, a second consumer) without touching the bucket's notification configuration.
2. **The Lambda runs in the VPC and reaches Kafka through an internal NLB** created by the AWS Load Balancer Controller for a second Strimzi listener (`type: loadbalancer`, TLS with the cluster CA, the NLB's security group admitting only the Lambda's). The controller is a Step 12 need anyway (the public ALB). Cost ≈ $0.54/day per NLB while the cluster is up (bootstrap + one broker); `make cluster-down` removes LoadBalancer Services before eks (step 1/4).
3. **The Lambda is a container image**: a second stage of `services/ingest/Dockerfile` with `awslambdaric`, pushed by `release.yml` as `steakllm/ingest:lambda-<sha>`; the handler already accepts EventBridge's shape.
4. **DynamoDB is one table** (`steakllm-catalog`, `pk`/`sk`, on-demand, point-in-time recovery, deletion protection) holding the catalog rows and the notifier's watch-list (`watch#<term>`); a second table would add a second backup, a second IAM scope and nothing else.
5. **Failures park, they do not vanish:** EventBridge retries twice, then the invocation goes to an SQS dead-letter queue with a 14-day retention and an alarm to the SNS topic; replaying the queue is a drill (07).
6. **Notifications are SNS to Thomas's email**, subscribed by Terraform from a GitHub variable (the address is not in git), confirmed by one click.

## Alternatives

- **S3 → Lambda direct.** Simpler by one resource. Rejected: no central filtering, no DLQ without extra code, and every later reader of "a file landed" would need the bucket's notification config edited.
- **SQS instead of Kafka for the pipeline events.** Cheaper, serverless. Rejected already in ADR-0006/0004: one reader, no replay, no ordering per document; drill 08 (rebuild Qdrant from the log) is the argument made executable.
- **An always-running poller instead of a Lambda** (a pod listing the bucket). Rejected in the Decisions table: Lambda is event glue that costs nothing between uploads; a poller costs a pod and adds latency.
- **A NodePort listener for the Lambda's door.** Free. Rejected: the bootstrap address is a node's private IP, which spot replaces (twice in one afternoon on Sep 4); the Lambda would have to look the node up by tag at cold start, and every reviewer would ask why not an NLB.
- **MSK (managed Kafka) reachable from the VPC natively.** Rejected on cost (~$70+/mo) and because Strimzi is the thing being learned.

## Consequences

- Two more Terraform modules (`data`, `pipeline`) with their own gates; the LB controller and a second Kafka listener in `platform/`; the summarizer gets its missing Pod Identity role.
- The Kafka door is the first LoadBalancer Service in the cluster: `cluster-down`'s first step now has something to remove, and the "never widen the public surface" rule holds because the NLB is internal and SG-scoped.
- Drills 05–10 become the acceptance of this ADR, not the code review.
