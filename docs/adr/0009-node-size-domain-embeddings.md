# 0009 — One t4g.xlarge for the platform; the public door deferred to Step 12; `all-minilm` on Ollama, image kept

Status: proposed (accepted when 8.2's apply is done)
Date: 2026-09-03

## Context

Step 8 puts the whole platform on the always-on node: Argo CD, Kafka, Prometheus/Grafana/Alertmanager, Loki and its collector, Qdrant, Ollama with its model, Open WebUI, External Secrets, the load-balancer controller, Tailscale, CoreDNS — and, from Step 10, the five workers. The public door needs a DNS name and a certificate. The embedding model must be the same locally and in the cluster or the vectors are not comparable. Thomas's answers on Sep 3 2026 fixed the four choices; this ADR records them with the alternatives.

## Decision

1. **The node is a `t4g.xlarge` (4 vCPU, 16 GiB), spot.** The memory budget for the platform on one node (field notes §2) comes to ≈ 6.3 GiB requested before the workers and ≈ 8 GiB with them; a t4g.large (8 GiB, ≈ 7.4 usable) leaves no headroom and would evict under Kafka's or Prometheus's first burst. Spot price at decision time $0.071/h (≈ $1.70/day, ≈ $51/month if always on; the dev-time posture makes it ≈ $0.35 per working hour). One variable in `infra/eks`; the node group rolls the node.
2. **The public door waits until everything else is ready (Step 12).** No domain, certificate, WAF, ALB or load-balancer controller in Step 8; the gateway is reached over the tailnet like every other service, and `aws elbv2 describe-load-balancers` staying empty is part of Step 8's done-when. When it comes: a domain registered in Route 53 (`steakllm.com` $16/year and `steakllm.dev` $17/year were available on Sep 3 2026); registration auto-creates the hosted zone, so Terraform must read it with a data source, not create it.
3. **Embeddings: `all-minilm` (384-dim) on Ollama, in the cluster as on the laptop**, until Step 11's evaluation job compares it with `bge-small` on the fixed question set. The Decisions table is corrected; the Qdrant collection dimension stays 384 either way.
4. **Ollama's 7 GB image is kept** (ADR-0005's open item): the model weights live on a persistent volume and the image is pulled once per node, so the cost is a few minutes on the first boot of a rebuilt cluster, not per pod. The self-built ONNX container stays the fallback if that minute ever matters (Step 9's GPU node does not run Ollama).

## Alternatives

- **Stay on t4g.large and split across two nodes later.** Two nodes double the fixed cost and put stateful pods across AZs (EBS cannot follow). Rejected: one bigger node is cheaper than two smaller ones and keeps every volume in one AZ.
- **On-demand xlarge.** No reclaims. Rejected: $0.134/h against $0.071/h for a node that Argo re-populates within minutes of a reclaim; Step 10 drills a forced replacement.
- **Build the public door now, as the Step 8 summary said.** Tests TLS and WAF early and gives a stable URL across rebuilds. Deferred by Thomas: nothing outside the tailnet needs the gateway before the demo, and every day of ALB + WAF is ≈ $0.80 for a door nobody knocks on; the cost of deferring is that Step 12 lands TLS, WAF and the ALB in one go (mitigated by writing the teardown pre-step for load balancers now, in 8.11).
- **An ALB over plain HTTP, no domain.** Free of the name. Rejected: API keys in clear text on the internet.
- **A domain at an external registrar, when the time comes.** Cheaper for some TLDs. Rejected: Route 53 registration hands us the zone, DNS validation and renewal in the same account and Terraform state; one bill.
- **`bge-small` now, as the Decisions table said.** A better model on paper. Rejected for now: the local stack has run `all-minilm` since Step 5, every local vector is 384-dim `all-minilm`, and switching models without an evaluation is a change with no measurement.
- **The ONNX embeddings container instead of Ollama.** ~400 MB, fast to pull. Rejected for now: one more thing to build and keep patched; the volume-cached model makes the 7 GB image a one-time cost.

## Consequences

- One node, one AZ: a spot reclaim takes the whole platform down for the minutes it takes the group to replace the node and Argo to re-schedule; acceptable in the dev-time posture, and measured in Step 10.
- Until Step 12 nothing answers from the internet: the security posture is stricter than designed for a while, and the e2e test runs against the tailnet address.
- The Qdrant collection is `all-minilm`-shaped; a model change is a re-index (Step 10's replay drill makes that a button, not a migration).
- kube-linter joins the CI gates for `platform/` (and `charts/` from 8.8), so a manifest without resource limits or probes is caught before Argo sees it.
