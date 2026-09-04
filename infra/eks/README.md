# infra/eks — the brain, and the one body

The Kubernetes control plane (7.3) and, in 7.4, one spot node with the add-ons. Applied by the pipeline behind the `production` gate; state key `eks/terraform.tfstate`; reads `infra/network`'s outputs through `terraform_remote_state`, so apply it after `network` (the matrices already run in that order).

| What | Where | Why |
|---|---|---|
| Cluster role (`AmazonEKSClusterPolicy`) | `cluster.tf` | What the control plane may do in our account: manage ENIs, load balancers, volumes |
| Log group, 14-day retention | `cluster.tf` | Created before the cluster so EKS does not create it with "never expire" |
| The cluster: private subnets, **private-only endpoint** (reached over the tailnet's subnet router — 8.9), five log streams, `STANDARD` support, no self-managed add-ons | `cluster.tf` | ADR-0008 and ADR-0010. Step 7's `/32` interim ended in Step 8.9 |
| Access entries: the apply role and the laptop identity, both cluster-admin | `cluster.tf` | The guest list. Nothing else can talk to the API. Step 8 adds per-service identities via Pod Identity, not here |
| Node role + launch template (40 GB gp3, IMDSv2, hop limit 1) + managed node group `cpu`: one t4g.large **spot**, one AZ, labels `steakllm.io/pool=cpu` | `nodegroup.tf` | The always-on body (ADR-0008). One AZ because EBS volumes are AZ-bound |
| Managed add-ons pinned: vpc-cni, kube-proxy, pod-identity-agent (before the node); coredns, metrics-server, ebs-csi (after) | `addons.tf` | The plumbing. The EBS driver wears its own IAM role through a Pod Identity association — the first pod with its own hat |

**Inputs that are not in git:** `TF_VAR_admin_principal_arn` (the laptop's IAM identity) is a repository variable, injected by `plan.yml` and `apply.yml`. (`TF_VAR_admin_cidr` was retired with the public endpoint in 8.9.)

**Cost:** $0.10/hour for the control plane from the first apply (≈ $73/month), plus cents for logs. It cannot be paused. The rebuild drill (7.6) is how it is turned off and on.

**First contact from the laptop** (after 7.3's apply):

```
aws eks update-kubeconfig --name steakllm --region us-east-1
kubectl get --raw /healthz        # ok
kubectl get nodes                 # one node, Ready, arm64, after 7.4
```
