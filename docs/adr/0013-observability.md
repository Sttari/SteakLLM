# 0013 — Observability: OpenTelemetry traces through Kafka headers into Tempo beside Loki; alerts by SNS with a runbook each; SLOs as promises with error budgets; a nightly eval of both backends

Status: proposed (accepted when 11.5's first alert has fired and arrived, and one trace spans upload to summary)
Date: 2026-09-06

## Context

Steps 8–10 built logs (JSON lines into Loki) and metrics (Prometheus, Grafana, Kafka and vLLM exporters). What is missing is the third signal and the discipline around all three: a way to follow one request or one document across five services and a Lambda; alerts that say what to do; promises with numbers; and an honest comparison of the two chat backends. Everything here must fit the dev-time cluster (one CPU node whose requests are near full) and cost nothing at rest.

## Decision

1. **Traces are OpenTelemetry, stored in Tempo beside Loki.** One SDK in `steakllm-common`, OTLP over HTTP to `tempo.logging.svc:4318`; FastAPI instrumentation in the gateway; a span per consumed event in the workers; **the trace context travels in Kafka headers** (`traceparent`) — the producer injects, the consumer loop extracts and continues — and the ingest Lambda starts the trace at the doorbell. Grafana links a log line's `trace_id` to its trace.
2. **Alerts go to the notifications SNS topic** through Alertmanager's `sns_configs`, with Pod Identity for Alertmanager's service account; every rule carries a `runbook_url` to `docs/runbooks/alerts/<name>.md`. No runbook, no alert.
3. **Three SLOs**, written in `docs/slo.md` with their SLIs as PromQL and a Grafana panel each: chat p95 latency, upload-to-searchable, doorbell success. Alerts on them are multi-window burn rates, not raw thresholds.
4. **Cost is a dashboard, not a report:** `ChatCompleted` tokens by backend from the gateway's `/metrics`, Bedrock at list price beside vLLM at GPU-hours × price ÷ tokens.
5. **A nightly eval** asks both backends the same twenty fact questions through the gateway (`x-prefer-backend`), scores on facts, writes to S3 and to a gauge on the dashboard. It runs before the GPU reaper so a summoned GPU never survives it.

## Alternatives

- **AWS X-Ray.** No cluster piece, native for the Lambda. Rejected: no Kafka propagation without custom code, a second UI away from Grafana, and the traces would leave the cluster's story.
- **Slack for alerts.** Familiar. Rejected for now: a webhook secret to mint and rotate, and the SNS topic with Thomas's email already exists and carries the DLQ alarm.
- **Latency-only alerts.** Simpler. Rejected: they page on a single slow minute; burn-rate alerts page when the promise is actually at risk.
- **A judge model for the eval.** Fashionable. Rejected: the fixtures state facts; exact-fact scoring is reproducible and free.

## Consequences

- Tempo adds one small pod and a 10 Gi volume (72 h retention) to a full CPU node; 11.7's request-budget decision comes first.
- The Lambda and the workers gain an OTel dependency (≈ 15 MB in the images); traces are sampled at 100% at our volume.
- The eval costs ≈ $0.25 a night (a ten-minute GPU, Bedrock tokens); the cost dashboard shows it.
