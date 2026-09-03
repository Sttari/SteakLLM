variable "region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "steakllm"
}

variable "cluster_name" {
  description = "The EKS cluster the Pod Identity associations bind to (infra/eks). A name, not a remote-state read, so plans succeed while the cluster is down."
  type        = string
  default     = "steakllm"
}

variable "documents_bucket" {
  description = "The documents bucket (created in Step 10). Named here so the gateway's and embedder's policies are scoped to it from day one."
  type        = string
  default     = "steakllm-documents-066591056087"
}

variable "catalog_table" {
  description = "The DynamoDB catalog (created in Step 10)."
  type        = string
  default     = "steakllm-catalog"
}

variable "notifications_topic" {
  description = "The SNS topic the notifier publishes to (created in Step 10)."
  type        = string
  default     = "steakllm-notifications"
}

variable "bedrock_model_id" {
  description = "The one Bedrock model the gateway may invoke (same as the plan role's, infra/bootstrap)."
  type        = string
  default     = "amazon.nova-micro-v1:0"
}

variable "secret_recovery_days" {
  description = "Secrets Manager keeps a deleted secret this long before it is gone for good; 7 is the minimum non-zero. A rebuilt platform can then re-create the same names."
  type        = number
  default     = 7
}
