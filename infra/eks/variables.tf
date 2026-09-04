variable "region" {
  description = "Same region as infra/network and infra/ecr."
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Tag value and name prefix."
  type        = string
  default     = "steakllm"
}

variable "cluster_name" {
  description = "The cluster's name; infra/network tagged its subnets kubernetes.io/cluster/<this>."
  type        = string
  default     = "steakllm"
}

variable "cluster_version" {
  description = "Kubernetes version. Pinned to the newest standard-support version at creation (Sep 2 2026: 1.36); bumped on purpose, one minor at a time, never left to age into extended support."
  type        = string
  default     = "1.36"
}

variable "admin_principal_arn" {
  description = "The laptop identity that gets cluster-admin through an access entry (an IAM user or role ARN; a repository variable, TF_VAR_admin_principal_arn)."
  type        = string
  validation {
    condition     = can(regex("^arn:aws:iam::[0-9]{12}:(user|role)/", var.admin_principal_arn))
    error_message = "admin_principal_arn must be an IAM user or role ARN."
  }
}

variable "apply_role_name" {
  description = "The pipeline's apply role (infra/bootstrap); it creates the cluster and gets an explicit access entry rather than the implicit creator-admin."
  type        = string
  default     = "steakllm-ci-apply"
}

variable "node_instance_types" {
  description = "The always-on node: any of these, whichever spot pool has capacity (Incident 27: t4g.xlarge alone scored 1/10 on spot placement; the mix scores 9/10). All arm64, 4 vCPU, 16 GiB (ADR-0009)."
  type        = list(string)
  default     = ["t4g.xlarge", "m6g.xlarge", "m7g.xlarge"]
}

variable "log_retention_days" {
  description = "Control-plane logs in CloudWatch. 14 days is enough to debug and costs cents."
  type        = number
  default     = 14
}
