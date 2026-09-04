# charts/vllm — Qwen2.5-7B-Instruct on the GPU pool

The chart behind `vllm.steakllm.svc:8000`, the address the gateway probes and routes to (ADR-0006, ADR-0011).

| Piece | What it does |
|---|---|
| `Deployment vllm` (0 replicas, `Recreate`) | on the `gpu` pool with the `nvidia.com/gpu` toleration; init container `weights` (aws-cli, `s3 sync` from the models bucket to an emptyDir on the node's NVMe, ≈ 80 s for 15 GB); container `vllm` (v0.28.0 from ECR, `vllm serve /models/qwen2.5-7b-instruct`, served as `Qwen/Qwen2.5-7B-Instruct`, `qwen2.5-7b-instruct`, `llm`, `docs`), uid 1000 with every cache under `/tmp`, read-only root, startup probe 10 min |
| `Service vllm` | ClusterIP 8000; only the gateway, the workers and Prometheus may reach it (`vllm-ingress`) |
| `ScaledObject vllm` | KEDA: chats or documents on Kafka in the last five minutes (Prometheus) → replicas 1; 900 s of silence → 0 |
| `ServiceMonitor vllm` | vLLM's `/metrics` (`vllm:generation_tokens_total`, `vllm:kv_cache_usage_perc`, `vllm:num_requests_running`) |
| `ServiceAccount vllm` | Pod Identity `steakllm/vllm` → role `steakllm-vllm` (read the models bucket) |

**Values that matter:** `model.*` (name, aliases, `maxModelLen` 8192, `gpuMemoryUtilization` 0.9, `dtype` half), `weights.*` (bucket, prefix, `sizeLimit`), `resources` (one GPU, ≤ 13 GiB host memory), `autoscaling.*` (topics, `pollingInterval`, `cooldownPeriod`), `metrics.serviceMonitor`.

**Who owns replicas:** KEDA. The Argo Application ignores `/spec/replicas` and syncs with `RespectIgnoreDifferences=true`. A hand `kubectl scale` is reverted within a poll; to hold vLLM at zero, `kubectl -n steakllm annotate scaledobject vllm autoscaling.keda.sh/paused-replicas=0` (what `make gpu-down` does); remove the annotation to resume.

**Drills:** `docs/chaos/02-summon.md`, `03-demand.md`, `04-reaper.md`; the load table `tests/load/chat_load.py` (Step 9.8, field notes §4).

**Known edges:** `enableServiceLinks: false` (the Service name would inject `VLLM_PORT`); no `--disable-log-requests` (gone in 0.28); the first token after a summon is ≈ 7–9 minutes away, Bedrock answers meanwhile.
