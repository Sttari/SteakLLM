# infra/eks — the brain, and the one body

The Kubernetes control plane (7.3) and, in 7.4, one spot node with the add-ons. Applied by the pipeline behind the `production` gate; state key `eks/terraform.tfstate`; reads `infra/network`'s outputs through `terraform_remote_state`, so apply it after `network` (the matrices already run in that order).

| What | Where | Why |
|---|---|---|
| Cluster role (`AmazonEKSClusterPolicy`) | `cluster.tf` | What the control plane may do in our account: manage ENIs, load balancers, volumes |
| Log group, 14-day retention | `cluster.tf` | Created before the cluster so EKS does not create it with "never expire" |
| The cluster: private subnets, private + public endpoint, public restricted to one `/32`, five log streams, `STANDARD` support, no self-managed add-ons | `cluster.tf` | ADR-0008. The `/32` is the interim admin door; Step 8 flips `endpoint_public_access` to `false` |
| Access entries: the apply role and the laptop identity, both cluster-admin | `cluster.tf` | The guest list. Nothing else can talk to the API. Step 8 adds per-service identities via Pod Identity, not here |

**Inputs that are not in git:** `TF_VAR_admin_cidr` (Thomas's address as `/32`) and `TF_VAR_admin_principal_arn` (the laptop's IAM identity) are repository variables, injected by `plan.yml` and `apply.yml`.

**Cost:** $0.10/hour for the control plane from the first apply (≈ $73/month), plus cents for logs. It cannot be paused. The rebuild drill (7.6) is how it is turned off and on.

**First contact from the laptop** (after 7.3's apply):

```
aws eks update-kubeconfig --name steakllm --region us-east-1
kubectl get --raw /healthz        # ok
kubectl get nodes                 # No resources found — until 7.4
```
