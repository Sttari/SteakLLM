# services/summarizer — `steakllm-summarizer`

Consumer group `steakllm-summarizer` on `documents` + `documents.retry`.

- `DocumentUploaded` → (skip if the catalog already says `summarized`) → fetch → extract text → ask the **gateway** (`/v1/chat/completions`, `model=llm`) for a three-sentence summary and three tags as JSON → catalog `summarized` → `SummaryReady` with `backend` (`vllm`/`bedrock`) and token counts.
- `DocumentDeleted` → clear the summary and tags (a missing row is fine).

It never talks to vLLM or Bedrock itself: the gateway's routing policy decides, and reports the answer in `x-backend`. The `x-prefer-vllm-seconds` hint (default 600) tells the gateway how long the summarizer is happy to wait for the GPU. Locally the vLLM stub is down, so every summary is `backend=bedrock` — the fallback path being exercised.

```
uv sync && uv run pytest                    # fakes, no stack
uv run pytest -m integration                # needs `make up`; uses a stub gateway until 6.7's real one
uv run --project services/summarizer steakllm-summarizer   # from the repo root; probes on :8080
```
