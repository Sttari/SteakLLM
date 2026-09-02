# services/embedder — `steakllm-embedder`

The librarian. Consumer group `steakllm-embedder` on `documents` + `documents.retry`.

- `DocumentUploaded` → fetch the bytes → verify the sha256 → extract text → chunk → embed (`/v1/embeddings`) → upsert into Qdrant with `point_id(doc_id, i)` → catalog `indexed` (never regressing `summarized`) → `DocumentIndexed`.
- `DocumentDeleted` → delete the document's points (filter on `doc_id`).
- Anything else → not our business.

Idempotent by construction: the same event twice rewrites the same points and leaves the counts unchanged.

```
uv sync && uv run pytest                     # fakes, no stack
uv run pytest -m integration                 # needs `make up`: a real event → points; the same event again → no change
uv run --project services/embedder steakllm-embedder     # from the repo root; probes on :8080
```
