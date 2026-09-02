variable "region" {
  description = "Region for the VPC; the cluster (infra/eks) and the repositories (infra/ecr) share it."
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Tag value, resource-name prefix, and the value of the karpenter.sh/discovery tag Step 9 searches for."
  type        = string
  default     = "steakllm"
}

variable "cluster_name" {
  description = "Name of the EKS cluster (infra/eks); subnets carry the kubernetes.io/cluster/<name> tag the AWS load-balancer controller expects."
  type        = string
  default     = "steakllm"
}

variable "vpc_cidr" {
  description = "The VPC's address range. /16 = 65,536 addresses; every pod takes one (VPC CNI), so the private subnets are large."
  type        = string
  default     = "10.42.0.0/16"
}

variable "azs" {
  description = "Two availability zones: one building can fail. The NAT instance and, for Step 8's EBS-backed pods, the node live in the first."
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "public_subnet_cidrs" {
  description = "One per AZ, for the load balancer (Step 8) and the NAT instance. /20 = 4,096 addresses each; more than enough."
  type        = list(string)
  default     = ["10.42.0.0/20", "10.42.16.0/20"]
}

variable "private_subnet_cidrs" {
  description = "One per AZ, for nodes and pods. /18 = 16,384 addresses each."
  type        = list(string)
  default     = ["10.42.128.0/18", "10.42.192.0/18"]
}

variable "nat_instance_type" {
  description = "The NAT instance: t4g.nano is ~$3/month and bursts to 5 Gbps, far above the platform's egress (ADR-0007)."
  type        = string
  default     = "t4g.nano"
}
