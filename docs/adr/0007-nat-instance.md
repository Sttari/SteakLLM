# 0007 — Egress through a NAT instance, not a NAT gateway; gateway endpoints for S3 and DynamoDB

Status: proposed (accepted when Step 7.2 is applied)
Date: 2026-09-02

## Context

Nodes live in private subnets with no route from the internet, but they must reach out: pull images from ECR, call AWS APIs, fetch Helm charts and model weights, talk to Bedrock. Something has to translate their private addresses to one public one — network address translation, NAT. The platform's idle budget is ~$100/month, of which the EKS control plane alone is $73. The always-on node is one t4g.large; egress volume is small (images once per deploy, API calls, Bedrock tokens); the one large transfer, model weights to the GPU node, is mirrored in S3 and reaches the node through an S3 endpoint, never the NAT (Step 9).

## Decision

**A NAT instance**: one `t4g.nano` running the fck-nat AMI (Amazon Linux 2023, arm64, maintained by the fck-nat project as an open-source replacement for AWS's retired NAT-instance AMI), in one public subnet, with `source_dest_check` off, an Elastic IP, and a security group that admits traffic only from the VPC's range. The private route table's default route points at the instance's network interface. Cost ≈ $3.07/month for the instance plus $3.65/month for the public IPv4 address (AWS charges for every public IPv4 since 2024); no per-GB processing charge.

**Gateway endpoints for S3 and DynamoDB** on both route tables: free, private routes to the two services the platform uses most (documents, weights, state; the catalog), so that traffic never crosses the NAT and never pays for it.

## Alternatives

- **NAT gateway.** Managed, highly available inside its AZ, scales to 100 Gbps. Rejected on cost: $32.85/month standing plus $0.045 per GB processed, about a third of the whole idle budget for a door the platform opens a few times a day. It is the documented upgrade path: replacing the instance's ENI with a `nat_gateway_id` in one route table is a one-line change and a ten-minute apply.
- **One NAT instance per AZ.** Removes the single point of failure. Rejected for now: doubles the cost for a failure mode whose blast radius is "image pulls and API calls from the other AZ stall until the instance is replaced", and Step 7 has one node in one AZ anyway. Revisit if a second always-on node lands in the other AZ.
- **No NAT: interface endpoints for everything.** ECR, STS, CloudWatch, Bedrock and more each need a paid interface endpoint (~$7/month each per AZ); Helm charts and GitHub have none. Rejected: more expensive than the gateway it avoids.
- **Nodes in public subnets with public IPs.** Free egress. Rejected: every node becomes an internet-facing host, which the security posture forbids (one public door: the ALB).

## Consequences

- Egress is a single point of failure in one AZ. Mitigation: the instance is in an autoscaling group of one so a dead instance is replaced within minutes, and the route is re-pointed by a small script on boot (fck-nat's own mechanism). Recorded as a known limitation in the runbook.
- Throughput is bounded by a t4g.nano (up to 5 Gbps burst, far above need). If Step 9's weights ever bypass the S3 endpoint this must be revisited.
- The one public IPv4 costs more than the instance. When IPv6 egress is practical for every dependency, drop it.
- The instance is a real EC2 host in our VPC: it gets patched by replacement (new AMI → new instance), never by hand.
