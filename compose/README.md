# compose — the local dev stack

The platform's supporting cast on your laptop, so the services can be built and tested against real Kafka, real object storage, a real vector store and a real LLM without touching the cluster (ADR-0005).

```
make up      # start everything, wait until healthy, run the one-shot inits (~20 s warm)
make demo    # drive the sample PDF through the whole pipeline by hand; run it twice
make ps      # who is up
make logs SERVICE=kafka
make down    # stop; data volumes are kept
make nuke    # stop AND delete the volumes (asks you to type "nuke")
```

Copy `.env.example` to `.env` first and fill in `AWS_PROFILE`. Needs a Docker engine (OrbStack) and `uv`.

| Service | Stands in for | Port on the Mac | Note |
|---|---|---|---|
| `minio` (+ `minio-init`) | S3 | 9000 API, 9001 console | same API; only the endpoint differs. Bucket created by the init |
| `dynamodb` (+ `dynamodb-init`) | DynamoDB | 8000 | Amazon's local build; `catalog` table created by the init |
| `kafka` (+ `kafka-init`) | Strimzi Kafka | 9092 | single node, KRaft; topics `documents`, `documents.retry`, `documents.dlq`, `chats` declared by the init; auto-create off |
| `qdrant` | Qdrant | 6333 REST, 6334 gRPC | the real thing |
| `ollama` (+ `ollama-init`) | the embedding server | 11434 | `all-minilm`, 384 dims, behind `/v1/embeddings`; weights cached in a volume |
| `vllm-stub` | a dead vLLM | 8081 | answers 503 on `/health` and `/v1/*`, on purpose |
| `open-webui` | Open WebUI | 3000 | chat UI, talks only to the gateway (Step 6) |
| Bedrock | Bedrock | — | not a container: the real service, per token, via your AWS profile |

Every long-running service has a healthcheck that makes a real call (not a port probe — see field notes, Incidents 14–16). Inside a container use `127.0.0.1`, never `localhost`.

`sample/quarterly-report.pdf` is the demo document (fictional; regenerate with `uv run compose/sample/make_sample.py`). `demo.py` is a `uv` script with inline dependencies — the dress rehearsal for Step 6, not a service.
