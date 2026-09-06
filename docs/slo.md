# SLOs (Step 11.5)

A service-level objective is a promise with a number; its indicator is the PromQL that measures it; the error budget is what the promise leaves room for over 30 days. Alerts fire on burn rate (how fast the budget goes), never on a single slow minute. Panels: the "SteakLLM — usage & cost" dashboard, bottom row.

| SLO | SLI (PromQL) | Objective | Budget / 30 d |
|---|---|---|---|
| Chat latency | `histogram_quantile(0.95, sum by (le) (rate(steakllm_chat_latency_seconds_bucket[30d])))` | p95 < 10 s (Bedrock) / < 15 s while vLLM warms | 1% of minutes |
| Upload → searchable | embedder group lag and `updated_at - uploaded_at` on catalog rows (exporter: 11.7 open item; the e2e test measures it today: 5.7 s) | < 60 s for 99% of uploads | 1% of uploads |
| Doorbell success | Lambda invocations that ended in the DLQ ÷ invocations (CloudWatch: Errors / Invocations) | 99.9% | 0.1% of rings |

Measured at acceptance (Sep 6 2026): chat p50 0.8 s (Bedrock) / 6 s (vLLM); upload → answered 7.3 s; the doorbell's only failures were deliberate (drill 07).
