# services/notifier — `steakllm-notifier`

The town crier. Consumer group `steakllm-notifier` on `documents` + `documents.retry`.

`SummaryReady` → does the **watch-list** (`WATCH_LIST`, a JSON list of terms) match a tag exactly or appear in the summary? → **claim** the event id in the catalog row (`ADD notified_event_ids`, conditional: row exists and id not yet there) → **send** through the sink: `NOTIFY_SINK=stdout` (a `notification` log line) locally, `NOTIFY_SINK=sns` + `SNS_TOPIC_ARN` in the cloud.

Exactly once per event: a replayed `SummaryReady` is refused by the conditional write and skipped; a *new* `SummaryReady` for the same document (a re-summary) is a new fact and notifies again. Claim-then-send means a crash in between loses one notification rather than sending twice — the right side to err on for alerts.

```
uv sync && uv run pytest                    # fakes + moto SNS
uv run pytest -m integration                # needs `make up`: the claim on real DynamoDB Local
uv run --project services/notifier steakllm-notifier   # from the repo root; probes on :8080
```
