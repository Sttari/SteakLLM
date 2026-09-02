# services/common — `steakllm-common`

What the five services share, so the policies in `services/README.md` exist once:

| Module | Gives you |
|---|---|
| `settings` | `get_settings()` — every `.env` key as a typed field, validated at start-up |
| `logging` | `configure(service)`, `get_logger(name)`, `bound(**ids)` — one JSON line per log call, ids attached |
| `kafka` | `make_producer`, `make_consumer`, `produce`, `ConsumerLoop` — batches, idempotent handler, retry → `.retry` → `.dlq`, SIGTERM |
| `clients` | `s3_client`, `catalog_table`, `qdrant_client`, `bedrock_client`, `embed` |
| `text` | `extract_text(body, content_type)` (PDF, Markdown, plain), `chunk(text, size, overlap)` — deterministic |
| `health` | `start_probe_server(port, ready)` — `/healthz`, `/readyz` |

```
uv sync
uv run pytest                    # unit tests (fakes, moto)
uv run pytest -m integration     # needs `make up`; proves the DLQ path on real Kafka with throwaway topics
```
