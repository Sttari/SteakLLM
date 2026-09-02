# infra/network — the neighbourhood

The VPC the cluster lives in. Applied by the pipeline (`apply.yml`, behind the `production` gate), never from the laptop. State key `network/terraform.tfstate`; `infra/eks` reads the outputs through `terraform_remote_state`.

| What | Where | Why |
|---|---|---|
| VPC `10.42.0.0/16` | `vpc.tf` | Every pod takes a VPC address (VPC CNI), so the range is big |
| 2 public subnets (`/20`) | `vpc.tf` | The ALB (Step 8) and the NAT instance; nothing else. No auto-assigned public IPs |
| 2 private subnets (`/18`) | `vpc.tf` | Nodes and pods; no route from the internet; tagged for internal ELBs and Karpenter discovery |
| Internet gateway + public route table | `vpc.tf` | The way in, for the public subnets only |
| Gateway endpoints for S3 and DynamoDB | `vpc.tf` | Free private roads; documents, weights, state and the catalog never cross the NAT |
| NAT instance (fck-nat, t4g.nano, ASG of one, static ENI + EIP) | `nat.tf` | The one door out, ≈ $3/month + $3.65 for the IPv4 (ADR-0007) |
| Default security group emptied | `vpc.tf` | Nothing gets "allow all inside the VPC" by accident |

Deliberately absent: flow logs (cost; a Step 10 drill turns them on), a second NAT (ADR-0007), IPv6 (revisit when every dependency speaks it).

**If the NAT dies:** the autoscaling group launches a replacement, which attaches the same ENI on boot; the route never changes. Expect two to three minutes of no egress. The Elastic IP is the address the egress drill and any allowlist see.
