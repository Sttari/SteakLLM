# 0012 — The cloud event pipeline: S3 → EventBridge → a Lambda in the VPC → Kafka through an internal NLB; DynamoDB single table with PITR; a dead-letter queue; SNS by email

Status: accepted (Sep 6 2026: upload → answered in 7.3 s over the tailnet; drills 05–10 pass; amended below)
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

## Amendments (Sep 5–6 2026, from building and drilling it)

- **The catalog is keyed by `doc_id`**, not the `pk`/`sk` single table decision 4 described: five services already addressed it that way (Step 6's contract). The notifier's watch-list is its own small table, `steakllm-watchlist`.
- **The Lambda finds the door itself.** A Terraform data lookup of the controller-made NLB broke every `cluster-up` while the cluster was down (Incident 47); the Lambda resolves the bootstrap NLB at start by the controller's `service.k8s.aws/stack` tag. Rule: modules that must apply on day zero may name what the cluster will create, never read it.
- **The cluster CA is part of the rebuild.** A new cluster mints a new Strimzi CA; `make kafka-ca` re-fills `steakllm/kafka-ca` after `cluster-up` (Incident 47c).
- **The Lambda needs HTTPS out through the NAT** for its one Secrets Manager call; the "no NAT, no internet" security group was a dependency list missing its first line (Incident 44). An interface endpoint (≈ $7/month) is the alternative if the list grows.
- **The door's NLBs must leave before the controller does.** `cluster-down` cascades the kafka Application first, waits for the LoadBalancer Services, keeps the controller until then, and refuses to tear eks down while a load balancer exists (Incident 46).
- **Service links are off on every pod chart** (`enableServiceLinks: false`): a Service named like a settings prefix injects `<NAME>_PORT=tcp://…` (Incidents 39, 45).
- **Cost while the cluster is up:** two internal NLBs ≈ $1.08/day; everything else in this ADR is pay-per-use at pennies.
- **Measured:** PUT → indexed 5.7 s → summarized 6.8 s → answered 7.3 s; rebuild of the index from the log 21 s for 17 documents; PITR restore 210 s; the doorbell's retries park an event after 285 s.
