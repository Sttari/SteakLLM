variable "region" {
  description = "Region for the repositories; must match the cluster's region (Step 7)."
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Tag value and repository name prefix."
  type        = string
  default     = "steakllm"
}

variable "services" {
  description = "One repository per service; names match services/<name> and the Helm charts."
  type        = list(string)
  default     = ["gateway", "embedder", "summarizer", "notifier", "ingest"]
}
