# 0011 — The GPU pool: Qwen2.5-7B-Instruct on one g6.xlarge, on-demand first, summoned by Karpenter and KEDA, weights and image mirrored into our account

Status: proposed (accepted when 9.5's summon drill meets the eight-minute target)
Date: 2026-09-04

## Context

Step 9 adds the one expensive machine: a GPU node that must exist only while there is work, arrive in under eight minutes, and never survive a forgotten evening. Four choices shape it: which model, which machine and how it is bought, how it is summoned and dismissed, and where the 15 GB of weights and the 10 GB serving image come from on every cold start. Facts gathered on Sep 4 2026: the account's G-instance quotas are 8 vCPUs for on-demand and for spot (granted in the prototype days); a g6.xlarge has 4 vCPUs, 16 GiB, one NVIDIA L4 with 22.9 GB usable, 250 GB of local NVMe, x86; on-demand $0.8048/h, spot $0.63–0.70/h, spot placement score 1/10 in every us-east-1 zone.

## Decision

1. **The model is `Qwen/Qwen2.5-7B-Instruct`** (15.2 GB fp16, Apache-2.0, ungated, 11 M downloads a month): a real 7B instruct model that fits the L4 with an 8k context at 90 % memory utilisation, a fair peer for Step 11's comparison with Nova Micro, and downloadable by a Job without a token or a licence click.
2. **The machine is a `g6.xlarge`, bought on-demand.** Spot saves 13–22 % today but scores 1/10 on placement: a summon that waits on spot capacity would miss the eight-minute promise and hand every first question to Bedrock. On-demand is the predictable path; a spot-first NodePool with on-demand fallback is Step 11's cost experiment, measured against the summon time.
3. **Karpenter owns the machine, KEDA owns the demand.** A NodePool limited to exactly one g6.xlarge with a GPU taint and `WhenEmpty` consolidation after fifteen minutes; vLLM as a Deployment at zero replicas scaled to one by KEDA on two Prometheus signals (messages into `chats`, messages into `documents` in the last five minutes) with a fifteen-minute cooldown. The gateway's circuit breaker and Bedrock fallback cover the warm-up.
4. **Weights and image are mirrored once into our account** — the weights to an S3 bucket (read over the free gateway endpoint onto the node's NVMe at start), the vLLM image (v0.28.0, amd64) to ECR — by Jobs on the CPU node. A cold start then pulls nothing from the internet.
5. **Two backstops:** Karpenter's `expireAfter` (24 h) and a nightly Lambda that shuts down any instance tagged as the GPU pool; `make cluster-down` refuses to tear the cluster down while a GPU node exists.

## Alternatives

- **A smaller model (3B) or a quantised 7B (AWQ/GPTQ, ≈ 5 GB).** Faster cold start, more KV cache. Rejected for now: the point of Step 11 is a like-for-like comparison of a self-hosted 7B against a hosted small model; quantisation is a follow-up experiment with the same chart.
- **Llama 3.1 8B Instruct.** The better-known peer. Rejected: gated (a Hugging Face token and a licence acceptance inside a Job), and the community licence adds a clause to the portfolio's README for no technical gain here.
- **Spot first.** Cheaper. Rejected for Step 9 on the placement score; revisited in Step 11 with the summon timer as the judge.
- **A managed GPU node group at zero desired size scaled by the cluster autoscaler.** Familiar. Rejected: the autoscaler is slower to react and knows nothing about pod-level GPU requests; Karpenter launches the exact machine a pending pod asks for and removes it when empty — the summon/dismiss loop in one component.
- **Pulling weights from Hugging Face on every cold start.** Zero infrastructure. Rejected: 15 GB through a t4g.nano NAT on every summon is minutes and money; the S3 endpoint is free and fast.
- **Keeping vLLM's image on Docker Hub.** Rejected for the same reason (10 GB through the NAT each time a node is new); ECR is in-region and the node role already pulls from it.

## Consequences

- Every summon costs ≈ 5 minutes of a $0.80/h machine (≈ $0.07) before the first token; the idle-to-removed window costs fifteen minutes (≈ $0.20) per burst. Cost follows demand, not the clock.
- The GPU node is x86 while the CPU node is arm64: vLLM's image is single-arch, our five services are multi-arch; nothing else changes.
- The models bucket and the ECR image survive cluster teardowns; Karpenter, KEDA and the NodePool are rebuilt by Argo with the cluster.
- A GPU node alive at teardown time would be orphaned and billing (Karpenter dies with the cluster): `cluster-down` checks, and the nightly Lambda is the last line.
