# 0008 — One spot node in a managed node group; the cluster API reachable from one address until the tailnet exists; Argo CD bootstrapped once by hand

Status: accepted (Sep 3 2026, after the 7.5 bootstrap drill and the 7.6 rebuild)
Date: 2026-09-02

## Context

Step 7 creates the cluster and the one always-on node, and installs Argo CD so that from then on the cluster equals git. Three questions decide most of the step's cost and its security shape: how the node is bought, who can reach the cluster's API before the admin door (Tailscale, Step 8) exists, and how the first GitOps controller gets into a cluster that has no GitOps controller yet. The rails: one public door (the ALB), never the Kubernetes API; nothing reaches the cluster except through git; only `infra/bootstrap` is ever applied from the laptop; the idle budget is ~$100/month.

## Decision

1. **One `t4g.large` bought as spot, in an EKS managed node group (min 1, desired 1, max 2).** Spot is spare capacity at roughly 60 % off (≈ $20/month against ≈ $49 on-demand); AWS may reclaim it with a two-minute warning. The managed node group replaces a reclaimed node automatically, and Argo's self-heal re-creates whatever was on it. Graviton (arm64) because it is the cheapest vCPU AWS sells and every image is already built for it.
2. **The cluster API endpoint is private *and* public, with public access restricted to one `/32` — Thomas's current address — until Step 8**, when the Tailscale operator (deployed by Argo) provides the admin door and the endpoint becomes private-only. Authentication is IAM (access entries) regardless; the `/32` is a second wall, not the only one. The address is a repository variable, not a file in git.
3. **Argo CD is bootstrapped once, by hand, from the laptop, in a drill named as such** (`helm install` of the pinned chart with values from `platform/argocd/values.yaml`, then `kubectl apply` of the root Application). From that moment Argo manages itself (an Application for its own chart) and everything under `platform/`; no human applies anything to the cluster again outside a named drill. Terraform builds only what the AWS API can build: network, cluster, node group, add-ons, access entries, Pod Identity associations.

## Alternatives

- **On-demand node.** Never reclaimed. Rejected on cost: $29/month more for a node whose loss costs a few minutes of self-healing. The Decisions table already priced the idle floor with a spot node.
- **Karpenter for the CPU node too.** One tool for all nodes. Rejected for Step 7: Karpenter needs a node to run on; the managed node group is that node. Karpenter arrives in Step 9 for the GPU pool.
- **Private-only endpoint from day one.** The cleanest posture. Rejected for Step 7 only: with no tailnet yet, neither the laptop nor CI could reach the API, so nothing could be bootstrapped. The `/32` interim is explicit, dated, and removed in Step 8.
- **Public endpoint open to the internet, IAM-authenticated.** AWS's default; it is what lets Terraform-in-CI reach the API. Rejected: the rails forbid a public Kubernetes API, and "authenticated" is one wall where the posture asks for two.
- **Argo installed by Terraform (the Step 7 summary's original wording).** Terraform's Helm provider must reach the API from wherever Terraform runs — CI — which needs the public endpoint above, or a self-hosted runner in the VPC (cost, upkeep), or a dynamic allowlist of the runner's address on every apply (a cluster update per run, brittle). Rejected in favour of one honest hand step.
- **Argo installed by a Kubernetes Job or EKS add-on.** No such add-on exists; a Job still needs something to apply it.

## Consequences

- Spot interruptions are a normal event. The platform must tolerate a node vanishing: PersistentVolumes are EBS (they survive and re-attach in the same AZ — so the node group is pinned to one AZ's subnet for Step 8's stateful pods, a constraint recorded here), and every workload is under Argo's self-heal. Step 10's drills include a forced node replacement.
- One interim public path exists between Step 7.3 and Step 8's tailnet, restricted to one address. Rotating Thomas's address (home network change) means updating one repository variable and one apply.
- Exactly one imperative step exists in the whole system: the Argo bootstrap. It is documented in `platform/README.md` and in the rebuild runbook, and the rebuild drill (7.6) proves it is repeatable.
- The apply role holds cluster-admin through an access entry; that is broader than Step 8's per-service roles will be, and is the same "narrow later" debt as ADR-0001 records for the apply role itself.

## Amendment (Sep 3 2026) — a dev-time cluster, not an always-on one

Thomas's decision at the end of Step 7: the platform should charge only while it is being worked on. The control plane ($2.40/day) cannot be paused, only removed, so the session ritual now ends with `teardown.yml` for `eks` and begins with `apply.yml` plus the one-minute Argo bootstrap — the rebuild drill (7.6) measured the round trip at 40 minutes, which Step 8.11 turns into two make targets and shortens by keeping the network up. Consequences: every EBS volume is lost with the cluster (acceptable before Step 10's backups: test data the pipeline regenerates); the ALB and anything else a controller creates outside Kubernetes must be deleted *before* the cluster goes (8.11); the "always-on small cluster" line in the Decisions table is amended, and the demo posture is revisited at Step 12.
