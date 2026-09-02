# infra/network — the VPC the cluster lives in: two AZs, private subnets for nodes, public subnets for
# the load balancer and the NAT instance, free gateway endpoints for S3 and DynamoDB (ADR-0007).
# Applied by the pipeline (apply.yml), never the laptop. State key: network/terraform.tfstate.
terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
