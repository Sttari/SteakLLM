# System map — who may talk to whom (Step 8)

The museum's floor plan: rooms (namespaces), what lives in each, and the doors between them. Every arrow below is a NetworkPolicy in `platform/network-policies/`; anything not drawn is denied in the application rooms. Platform rooms (grey) are not walled until Step 10.

```mermaid
flowchart LR
    subgraph laptop["Thomas's laptop (tailnet · until 8.9: port-forward via the /32)"]
      T[tailscale / kubectl]
    end
    subgraph tailscale["tailscale (baseline)"]
      TS[proxies + connector]
    end
    subgraph steakllm["steakllm (restricted)"]
      GW[gateway :8000]
      W[workers — Step 10]
    end
    subgraph kafka["kafka (baseline)"]
      K[(Kafka :9092 · metrics :9404)]
      SO[strimzi operator · entity operator]
    end
    subgraph qdrant["qdrant (restricted)"]
      Q[(Qdrant :6333)]
    end
    subgraph ollama["ollama (restricted)"]
      O[Ollama :11434]
    end
    subgraph webui["open-webui (baseline)"]
      UI[Open WebUI :8080]
    end
    subgraph platform["platform rooms — not walled yet"]
      P[Prometheus]
      A[Alloy → Loki]
      AR[Argo CD]
      ES[External Secrets]
    end
    AWS[(AWS: Bedrock · S3 · DynamoDB · SNS · Secrets Manager)]

    T -->|tailnet| TS
    TS --> GW & UI & P & AR
    UI -->|/v1| GW
    GW --> K & Q & O
    GW -->|443 via NAT| AWS
    W --> K & Q & O & GW
    W -->|443 via NAT| AWS
    SO --> K
    P -->|scrape| K & Q & GW
    ES -->|443 via NAT| AWS
    O -->|443, model pull once| AWS
```

## Rooms

| Namespace | Pod Security | Lives here | Walls |
|---|---|---|---|
| `steakllm` | restricted | gateway (8.8), the four workers (Step 10) | default-deny; egress to Kafka, Qdrant, Ollama, AWS:443; ingress from Open WebUI, Prometheus, Tailscale, itself |
| `kafka` | baseline | Strimzi operator, `steakllm` Kafka (KRaft, 1 node), entity operator | default-deny; ingress 9092 from `steakllm` and itself, 9404 from Prometheus; egress within the room and to the API server |
| `qdrant` | restricted | Qdrant | default-deny; ingress 6333 from `steakllm` and Prometheus |
| `ollama` | restricted | Ollama + model volume, pull job | default-deny; ingress 11434 from `steakllm` and itself; egress 443 (the pull) |
| `open-webui` | baseline | Open WebUI + its redis | default-deny; ingress 8080 from Tailscale; egress to the gateway only |
| `monitoring` | privileged (warn baseline) | Prometheus, Alertmanager, Grafana, node-exporter, kube-state-metrics | open (platform) |
| `logging` | privileged (warn baseline) | Loki, Alloy | open (platform) |
| `argocd` | — | Argo CD | open (platform) |
| `external-secrets` | restricted | ESO | open (platform) |
| `tailscale` | baseline | operator, proxies, connector (8.9) | open (platform) |

## Doors

- **Public door:** none until Step 12 (`aws elbv2 describe-load-balancers` is empty).
- **Admin door:** the tailnet (8.9). Until then, `kubectl port-forward` from the one allowed address.
- **The way out:** the NAT instance (ADR-0007) for AWS APIs and image pulls; S3 and DynamoDB take the free gateway endpoints.

## The proof (8.10)

A throwaway pod in `default` cannot reach `steakllm-kafka-bootstrap.kafka.svc:9092` (the connection times out); the gateway's pod can (its `/readyz` is 200, which is a Kafka metadata call); Prometheus still scrapes every target. Recorded in `PLAN.md` 8.10 with the date.
