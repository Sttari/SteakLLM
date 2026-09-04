variable "region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "steakllm"
}

variable "cluster_name" {
  description = "The EKS cluster (infra/eks). A name, not a remote-state read, so plans succeed while the cluster is down."
  type        = string
  default     = "steakllm"
}

variable "node_role_name" {
  description = "infra/eks's node role; Karpenter's EC2NodeClass names it and Karpenter builds the instance profile from it."
  type        = string
  default     = "steakllm-eks-node"
}

variable "gpu_nodepool" {
  description = "The Karpenter NodePool name; the reaper and cluster-down look for instances tagged karpenter.sh/nodepool = this."
  type        = string
  default     = "gpu"
}

variable "reaper_schedule" {
  description = "When the nightly reaper runs (EventBridge cron, UTC). 03:00 UTC is 23:00 on the US east coast."
  type        = string
  default     = "cron(0 3 * * ? *)"
}

variable "vllm_image_repository" {
  description = "ECR repository for the mirrored vLLM image (immutable tags, like the five services)."
  type        = string
  default     = "steakllm/vllm"
}
