# services/contracts — the event contracts

The envelope, the five event schemas, one example per event, the compatibility test, and the idempotency rules (Step 4). Python package `steakllm-contracts`, installed by every service.

```
uv sync            # install (creates .venv/, writes uv.lock)
uv run pytest      # validate examples, run the compatibility test
```

*(Rules and schema descriptions are filled in during 4.3–4.6.)*
