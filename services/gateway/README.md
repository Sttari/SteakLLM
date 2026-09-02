# services/gateway — `steakllm-gateway`

The front desk and the one public door. FastAPI, speaking the OpenAI chat contract.

| Route | Does |
|---|---|
| `GET /healthz`, `GET /readyz` | probes |
| `GET /v1/models` | `llm` (chat) and `docs` (chat over your documents — 6.8) |
| `POST /v1/chat/completions` | the chat route, streaming or not; `Authorization: Bearer <key>` required |
| `GET /docs` | OpenAPI |

**Routing policy** (`router.py`): per request, probe vLLM `/health` (300 ms, cached 2 s) → vLLM (passthrough) or Bedrock (Converse, translated to the OpenAI shape) and bump the demand signal. **Circuit breaker**: 3 consecutive vLLM failures → open 60 s (Bedrock, no probes) → half-open (one probe) → closed on success. A vLLM call that fails mid-request falls back too. Every response carries `x-backend`, `x-tokens-in`, `x-tokens-out`, `x-trace-id`; every completion emits `ChatCompleted` on `chats` with a hashed key id (never the key).

Locally the vLLM stub always answers 503, so every response is `x-backend: bedrock` — the fallback path, exercised on every request.

```
uv sync && uv run pytest                        # fakes, no stack, no Bedrock
uv run pytest -m integration                    # needs `make up` + Bedrock (pennies): real fallback, real event
uv run --project services/gateway steakllm-gateway     # from the repo root; :8000
curl -s localhost:8000/v1/chat/completions -H "Authorization: Bearer $GATEWAY_API_KEY" -H 'Content-Type: application/json' \
  -d '{"model":"llm","messages":[{"role":"user","content":"Say hi in five words."}]}' -i
```
