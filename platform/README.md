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

Reading it: `kubectl -n argocd get applications` — every row `Synced` / `Healthy`. The floor plan of who may talk to whom is `docs/system-map.md`; the reasons are ADR-0009 and ADR-0010.

## The bootstrap drill — exactly once per cluster (`make cluster-up` does it)

Argo cannot install itself into a cluster that has no Argo. The one hand step in the whole system (ADR-0008), run from the laptop with the cluster-admin access entry:

```
helm repo add argo https://argoproj.github.io/argo-helm && helm repo update argo
helm install argocd argo/argo-cd --version 10.7.0 --namespace argocd --create-namespace -f platform/argocd/values.yaml --wait
kubectl apply -f platform/root.yaml
```

Then Argo reads `platform/apps/`, finds `argocd.yaml`, adopts its own installation, and builds the rest wave by wave (about ten minutes on a fresh cluster; Kafka and the model pull are the slow ones). From that moment every change, including to Argo, is a pull request.

**The UI, from the laptop only:** `kubectl -n argocd port-forward svc/argocd-server 8080:80`, `http://localhost:8080`, user `admin`, password `kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d` (rotated behind the tailnet in 8.9).

**Proving self-heal:** `kubectl -n argocd scale deploy argocd-repo-server --replicas=2` — back to 1 within seconds (measured: 6 s).

**Never** `kubectl apply` anything here outside a drill named in `PLAN.md`; if the cluster is wrong, git is wrong — fix it there.
