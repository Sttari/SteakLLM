# 0009 — One t4g.xlarge for the platform; a Route 53 domain; `all-minilm` on Ollama, image kept

Status: proposed (accepted when 8.2's apply and the domain registration are done)
Date: 2026-09-03

## Context

Step 8 puts the whole platform on the always-on node: Argo CD, Kafka, Prometheus/Grafana/Alertmanager, Loki and its collector, Qdrant, Ollama with its model, Open WebUI, External Secrets, the load-balancer controller, Tailscale, CoreDNS — and, from Step 10, the five workers. The public door needs a DNS name and a certificate. The embedding model must be the same locally and in the cluster or the vectors are not comparable. Thomas's answers on Sep 3 2026 fixed the four choices; this ADR records them with the alternatives.

## Decision

1. **The node is a `t4g.xlarge` (4 vCPU, 16 GiB), spot.** The memory budget for the platform on one node (field notes §2) comes to ≈ 6.3 GiB requested before the workers and ≈ 8 GiB with them; a t4g.large (8 GiB, ≈ 7.4 usable) leaves no headroom and would evict under Kafka's or Prometheus's first burst. Spot price at decision time $0.071/h (≈ $1.70/day, ≈ $51/month if always on; the dev-time posture makes it ≈ $0.35 per working hour). One variable in `infra/eks`; the node group rolls the node.
2. **A domain registered in Route 53** (name chosen by Thomas at purchase; `steakllm.com` at $16/year and `steakllm.dev` at $17/year were both available). Registration auto-creates the hosted zone ($0.50/month), so `infra/platform` reads the zone with a data source instead of creating one — a mismatch there would silently break DNS validation of the certificate.
3. **Embeddings: `all-minilm` (384-dim) on Ollama, in the cluster as on the laptop**, until Step 11's evaluation job compares it with `bge-small` on the fixed question set. The Decisions table is corrected; the Qdrant collection dimension stays 384 either way.
4. **Ollama's 7 GB image is kept** (ADR-0005's open item): the model weights live on a persistent volume and the image is pulled once per node, so the cost is a few minutes on the first boot of a rebuilt cluster, not per pod. The self-built ONNX container stays the fallback if that minute ever matters (Step 9's GPU node does not run Ollama).

## Alternatives

- **Stay on t4g.large and split across two nodes later.** Two nodes double the fixed cost and put stateful pods across AZs (EBS cannot follow). Rejected: one bigger node is cheaper than two smaller ones and keeps every volume in one AZ.
- **On-demand xlarge.** No reclaims. Rejected: $0.134/h against $0.071/h for a node that Argo re-populates within minutes of a reclaim; Step 10 drills a forced replacement.
- **A domain at an external registrar.** Cheaper for some TLDs. Rejected: Route 53 registration hands us the zone, DNS validation and renewal in the same account and Terraform state; one bill.
- **No domain: the ALB's DNS name and a self-signed certificate.** Rejected: browsers reject it, WAF and ACM expect a name, and the portfolio's public door should look like one.
- **`bge-small` now, as the Decisions table said.** A better model on paper. Rejected for now: the local stack has run `all-minilm` since Step 5, every local vector is 384-dim `all-minilm`, and switching models without an evaluation is a change with no measurement.
- **The ONNX embeddings container instead of Ollama.** ~400 MB, fast to pull. Rejected for now: one more thing to build and keep patched; the volume-cached model makes the 7 GB image a one-time cost.

## Consequences

- One node, one AZ: a spot reclaim takes the whole platform down for the minutes it takes the group to replace the node and Argo to re-schedule; acceptable in the dev-time posture, and measured in Step 10.
- The domain renews yearly on the card; `auto-renew` is on so the public door does not vanish with a forgotten email.
- The Qdrant collection is `all-minilm`-shaped; a model change is a re-index (Step 10's replay drill makes that a button, not a migration).
- kube-linter joins the CI gates for `platform/` (and `charts/` from 8.8), so a manifest without resource limits or probes is caught before Argo sees it.
