# infra/network — the neighbourhood

The VPC the cluster lives in. Applied by the pipeline (`apply.yml`, behind the `production` gate), never from the laptop. State key `network/terraform.tfstate`; `infra/eks` reads the outputs through `terraform_remote_state`.

| What | Where | Why |
|---|---|---|
| VPC `10.42.0.0/16` | `vpc.tf` | Every pod takes a VPC address (VPC CNI), so the range is big |
| 2 public subnets (`/20`) | `vpc.tf` | The ALB (Step 8) and the NAT instance; nothing else. No auto-assigned public IPs |
| 2 private subnets (`/18`) | `vpc.tf` | Nodes and pods; no route from the internet; tagged for internal ELBs and Karpenter discovery |
| Internet gateway + public route table | `vpc.tf` | The way in, for the public subnets only |
| Gateway endpoints for S3 and DynamoDB | `vpc.tf` | Free private roads; documents, weights, state and the catalog never cross the NAT |
| NAT instance (fck-nat, t4g.nano; the static ENI with the EIP is its primary interface) | `nat.tf` | The one door out, ≈ $3/month + $3.65 for the IPv4 (ADR-0007, Incident 26) |
| Default security group emptied | `vpc.tf` | Nothing gets "allow all inside the VPC" by accident |

Deliberately absent: flow logs (cost; a Step 10 drill turns them on), a second NAT (ADR-0007), IPv6 (revisit when every dependency speaks it).

**If the NAT dies:** hardware failure → EC2 auto-recovery restarts it on new hardware with the same ENI (minutes, no change to routes). Anything else → `terraform apply -replace=aws_instance.nat` through the pipeline; the ENI, EIP and route stay. To patch the AMI, the same command on purpose (`ignore_changes = [ami]` keeps an unrelated apply from replacing the door). Debug with `aws ssm start-session --target $(terraform output -raw nat_instance_id)`; there is no SSH. The Elastic IP is the address the egress drill and any allowlist see.
