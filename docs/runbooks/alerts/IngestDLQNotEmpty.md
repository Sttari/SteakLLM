# IngestDLQNotEmpty

**Symptom:** A doorbell event failed twice and is parked; an upload is not in the pipeline.

**Look at:**
- the Lambda's log group /aws/lambda/steakllm-ingest for the failing invocation
- the Kafka door: NLBs active? the cluster CA in steakllm/kafka-ca current (make kafka-ca after a rebuild)?

**Do:** fix the cause, then `uv run tests/chaos/replay_dlq.py <queue-url> steakllm-ingest`; a human purges the queue afterwards (drill 07)

**Escalate:** if the fix is not in this page, write the incident in docs/field-notes.md §3 and add what you learned here.
