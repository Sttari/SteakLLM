# services/ingest — `steakllm-ingest`

The S3 doorbell: **validate · hash · record · produce · walk away.** In the cloud a Lambda invoked by EventBridge with an S3 event record (Step 10); locally the same handler fed synthetic records by a CLI.

- `ObjectCreated` under `quarantine/` → size and type limits → stream-hash to `doc_id` → catalog row `uploaded` (never regressing an indexed document) → `DocumentUploaded`.
- Limit violated → object moved to `rejected/` → `DocumentDeleted` with reason `quarantine_rejected`.
- `ObjectRemoved` under `quarantine/` → catalog row deleted → `DocumentDeleted` with reason `user_request`.

```
uv sync && uv run pytest                                   # moto + fakes, no stack
uv run steakllm-ingest upload compose/sample/quarterly-report.pdf   # needs `make up`
uv run steakllm-ingest delete quarantine/2026/09/02/quarterly-report.pdf
uv run steakllm-ingest watch                               # poll quarantine/, ring for new objects
```

`lambda_handler(event, context)` in `main.py` is what Step 10 deploys.
