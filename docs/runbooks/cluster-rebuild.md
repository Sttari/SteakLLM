# Runbook — rebuild the cluster from nothing

The platform is cattle: everything below `infra/bootstrap` can be removed and rebuilt from git. This runbook is the measured proof (Step 7.6) and the procedure for the day it is needed for real (a broken cluster, a region move, a cost pause).

**What survives a rebuild:** the state bucket and the CI roles (`bootstrap`), the ECR images (`ecr`), everything in git. **What is lost:** every Kubernetes object including Argo CD and, in later steps, every EBS volume (Kafka log, Qdrant vectors, Prometheus history) — Step 10's backups exist for those; the NAT's Elastic IP (a new one is allocated; update any allowlist); the control-plane log group.

## Order

Removal runs *down* the dependency chain, rebuild runs *up* it. Each teardown is a `workflow_dispatch` of `teardown.yml` with the module name typed twice, behind the production gate; each rebuild is a `workflow_dispatch` of `apply.yml` (one gate per module) followed by the one hand step.

| # | Action | How | Expect | Measured (7.6) |
|---|---|---|---|---|
| 1 | Remove the cluster (node group, add-ons, control plane, log group, roles) | `gh workflow run teardown.yml -f module=eks -f confirm=eks` → approve | ~10–12 min (the control plane is slow to delete) | — |
| 2 | Remove the network (NAT instance, EIP, endpoints, subnets, VPC) | `gh workflow run teardown.yml -f module=network -f confirm=network` → approve | ~2–3 min | — |
| 3 | Rebuild both | `gh workflow run apply.yml` → approve ecr, network, eks in turn | network ~2 min, eks ~11 + ~3 min | — |
| 4 | Point the laptop at the new cluster | `aws eks update-kubeconfig --name steakllm --region us-east-1` | `kubectl get nodes` → one Ready node | — |
| 5 | The one hand step: bootstrap Argo CD (see `platform/README.md`) | `helm install … --wait && kubectl apply -f platform/root.yaml` | ~1 min; `root` and `argocd` Synced/Healthy within ~2 min | — |
| 6 | Confirm | `kubectl -n argocd get applications`; egress drill from `PLAN.md` 7.4 | all Synced/Healthy; NAT EIP printed | — |

**Total, first measurement (Sep 2026):** — (filled by 7.6).

## Before removing anything

- Say what is lost, out loud, per the safety rails: the cluster and everything on it; then the VPC and its Elastic IP.
- Nothing is applying: `gh run list --workflow apply --limit 1` shows a completed run (the two workflows share a concurrency lock per module, but look anyway).
- From Step 10 on: the backups exist and are recent (DynamoDB PITR, Qdrant snapshot in S3).

## If a teardown fails halfway

`terraform plan -destroy` again reads the state and removes what is left; re-dispatch the same module. The most common stragglers: a security group still referenced by an ENI the cluster left behind (wait a minute, retry), a log group re-created by a late log delivery (delete it by hand — the one exception — or ignore; it costs nothing empty).
