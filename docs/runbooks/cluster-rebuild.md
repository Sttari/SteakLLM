# Runbook — rebuild the cluster from nothing

The platform is cattle: everything below `infra/bootstrap` can be removed and rebuilt from git. This runbook is the measured proof (Step 7.6) and the procedure for the day it is needed for real (a broken cluster, a region move, a cost pause).

**What survives a rebuild:** the state bucket and the CI roles (`bootstrap`), the ECR images (`ecr`), everything in git. **What is lost:** every Kubernetes object including Argo CD and, in later steps, every EBS volume (Kafka log, Qdrant vectors, Prometheus history) — Step 10's backups exist for those; the NAT's Elastic IP (a new one is allocated; update any allowlist); the control-plane log group.

## The everyday version (Step 8.11)

`make cluster-down` at the end of a session: **first empties the GPU pool** (`make gpu-down`: KEDA paused at 0, vLLM to 0, NodeClaims removed so Karpenter terminates the machine now; `make gpu-check` then refuses to continue while any instance tagged `karpenter.sh/nodepool=gpu` exists — Karpenter cannot clean up a node after Karpenter is gone, and the nightly reaper Lambda is the net behind that), then removes every Ingress and LoadBalancer Service first, then takes the workloads down *through Argo* (a cascade finalizer on each workload Application, then the root Application is removed — otherwise self-heal re-creates every pod and a claim can never be released; Incident 33 — and the Tailscale apps are kept alive until the end, because the subnet router is the laptop's only path to the private API; Incident 33b), then (a controller-made ALB outlives the cluster and keeps billing; none exist before Step 12), waits until `aws elbv2 describe-load-balancers` is empty, removes every PersistentVolumeClaim and waits until no PVC-backed EBS volume remains (a torn-down cluster cannot delete its own disks; an orphaned volume keeps billing — found Sep 3 2026, 82 GB), dispatches `teardown.yml` for `eks`, approves its gate, waits, prints the meter check. `make cluster-up` at the start: dispatches `apply.yml`, approves the five gates in order, refreshes kubeconfig, then `make bootstrap-argo`: since the API is private-only (8.9) and the tailnet router lives inside the cluster, the bootstrap goes through a Session Manager port-forward via the NAT instance (`aws ssm start-session … AWS-StartPortForwardingSessionToRemoteHost`, local 6443 → the API, TLS name pinned), installs Argo, applies the root Application, waits for the Tailscale Connector, then closes the tunnel and restores the kubeconfig (Incident 34). Needs `brew install --cask session-manager-plugin` once. The pre-step cannot live inside `teardown.yml`: the cluster's API is never reachable from a GitHub runner (one `/32`, then private-only), so the laptop does it.

## Order

Removal runs *down* the dependency chain, rebuild runs *up* it. Each teardown is a `workflow_dispatch` of `teardown.yml` with the module name typed twice, behind the production gate; each rebuild is a `workflow_dispatch` of `apply.yml` (one gate per module) followed by the one hand step.

| # | Action | How | Expect | Measured (7.6) |
|---|---|---|---|---|
| 1 | Remove the cluster (node group, add-ons, control plane, log group, roles) | `gh workflow run teardown.yml -f module=eks -f confirm=eks` → approve | ~10–12 min (the control plane is slow to delete) | 10 min (dispatch 01:30:34Z → done 01:40:52Z; the control plane 3 m 23 s of it) |
| 2 | Remove the network (NAT instance, EIP, endpoints, subnets, VPC) | `gh workflow run teardown.yml -f module=network -f confirm=network` → approve | ~2–3 min | 3 min (27 resources; the NAT instance 1 m 21 s) |
| 3 | Rebuild both | `gh workflow run apply.yml` → approve ecr, network, eks in turn | network ~2 min, eks ~11 + ~3 min | 22 min with gate waits (dispatch 01:44:42Z → eks done 02:06:58Z): ecr 11 s, network 44 s, cluster 13 m 22 s, node group 1 m 58 s |
| 4 | Point the laptop at the new cluster | `aws eks update-kubeconfig --name steakllm --region us-east-1` | `kubectl get nodes` → one Ready node | seconds |
| 5 | The one hand step: bootstrap Argo CD (see `platform/README.md`) | `helm install … --wait && kubectl apply -f platform/root.yaml` | ~1 min; `root` and `argocd` Synced/Healthy within ~2 min | release deployed 02:09:47Z; both Synced/Healthy by 02:11:14Z. Sep 4: `make cluster-up` end to end 15 min 44 s |
| 6 | Confirm | `kubectl -n argocd get applications`; egress drill from `PLAN.md` 7.4 | all Synced/Healthy; NAT EIP printed | Synced/Healthy; self-heal 6 s; egress pod saw the new EIP 54.235.98.175 |

**Total, first measurement (Sep 3 2026):** **40 minutes** from the first dispatch to Argo Synced on the new cluster (01:30:34Z → 02:10:35Z), of which about 14 minutes removing, 22 rebuilding (three approval waits included), 2 bootstrapping. The variable part is EKS itself: 10 m 36 s to create the first time, 13 m 22 s the second.

## Before removing anything

- Say what is lost, out loud, per the safety rails: the cluster and everything on it; then the VPC and its Elastic IP.
- Nothing is applying: `gh run list --workflow apply --limit 1` shows a completed run (the two workflows share a concurrency lock per module, but look anyway).
- From Step 10 on: the backups exist and are recent (DynamoDB PITR, Qdrant snapshot in S3).

## If a teardown fails halfway

`terraform plan -destroy` again reads the state and removes what is left; re-dispatch the same module. The most common stragglers: a security group still referenced by an ENI the cluster left behind (wait a minute, retry), a log group re-created by a late log delivery (delete it by hand — the one exception — or ignore; it costs nothing empty).
