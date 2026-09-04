# platform — what runs on the cluster, as Argo CD Applications

Nothing reaches the cluster except through git. Argo CD watches `platform/apps/` and makes the cluster match it: automated sync, prune (removed from git → removed from the cluster), self-heal (hand edits are reverted). Sync waves order the rooms: namespaces (-2) → storage (-1) → operators (0–2) → data services (3) → the UI and the gateway (4) → the walls (5).

| Application | Wave | Chart / path | Version | Values | Needs |
|---|---|---|---|---|---|
| `namespaces` | -2 | `platform/namespaces` | — | — | — |
| `storage` | -1 | `platform/storage` | — | — | the EBS CSI add-on (infra/eks) |
| `argocd` | 0 | argo-helm `argo-cd` | 10.7.0 | `platform/argocd/values.yaml` | bootstrapped once by hand (below) |
| `external-secrets` | 0 | `external-secrets` | 2.10.0 | `platform/external-secrets/values.yaml` | Pod Identity `external-secrets/external-secrets` (infra/platform) |
| `secret-stores` | 1 | `platform/secret-stores` | — | — | the three Secrets Manager slots, filled |
| `monitoring` | 2 | `kube-prometheus-stack` | 88.6.4 | `platform/monitoring/values.yaml` | `grafana-admin` from secret-stores; gp3 |
| `loki` | 2 | `loki` | 7.3.0 | `platform/loki/values.yaml` | gp3 |
| `strimzi` | 2 | `strimzi-kafka-operator` | 1.2.0 | `platform/strimzi/values.yaml` | — |
| `alloy` | 3 | `alloy` | 1.12.1 | `platform/alloy/values.yaml` | Loki; the `logging` room is `privileged` (hostPath) |
| `kafka` | 3 | `platform/kafka` | Strimzi API `v1` | — | the operator's CRDs; gp3 |
| `qdrant` | 3 | `qdrant` | 1.19.0 | `platform/qdrant/values.yaml` | gp3; unprivileged image (restricted room) |
| `ollama` | 3 | `platform/ollama` | image 0.33.3 | — | gp3; egress 443 for the one model pull |
| `open-webui` | 4 | `open-webui` | 16.5.0 | `platform/open-webui/values.yaml` | `gateway-keys` in its room; the gateway |
| `gateway` | 4 | `charts/gateway` (this repo) | image `sha-3432f6a` | inline `image.tag` | Kafka, Qdrant, Ollama; Pod Identity `steakllm/gateway`; `gateway-keys` |
| `network-policies` | 5 | `platform/network-policies` | — | — | NetworkPolicy enforcement on in the VPC CNI (infra/eks) |
| `tailscale` (8.9) | 2 | `tailscale-operator` | 1.102.3 | `platform/tailscale/values.yaml` | the `steakllm/tailscale` slot filled with the OAuth client |
| `gpu-mirror` (9.3) | 4 | `platform/gpu-mirror` | crane:debug (by digest), python 3.12 | — | Pod Identity `steakllm/mirror`; two guarded Jobs (weights → bucket, image → ECR) |
| `karpenter` (9.4) | 3 | `karpenter` (OCI, public.ecr.aws) | 1.14.1 | `platform/karpenter/values.yaml` | Pod Identity `karpenter/karpenter`, queue `steakllm-karpenter` (infra/gpu); one replica on the CPU node |
| `gpu-pool` (9.4) | 5 | `platform/gpu-pool` | AMI `al2023@v20260827`, plugin v0.20.0 | — | EC2NodeClass `gpu`, NodePool `gpu` (one of g6.xlarge / g6.2xlarge / g5.xlarge, on-demand, WhenEmpty 15m, expireAfter 24h), NVIDIA device plugin in kube-system |
| `keda` (9.6) | 3 | `keda` (kedacore) | 2.20.2 | `platform/keda/values.yaml` | the ScaledObject on vLLM lives in `charts/vllm`; reads kube-prometheus-stack |
