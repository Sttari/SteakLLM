variable "region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "steakllm"
}

variable "quarantine_prefix" {
  description = "Uploads land here first (the gateway's presigned PUT); the ingest Lambda moves what passes validation. Expires after quarantine_days."
  type        = string
  default     = "quarantine/"
}

variable "quarantine_days" {
  type    = number
  default = 7
}

variable "notify_email" {
  description = "The SNS email subscriber (Thomas). From the GitHub variable TF_VAR_NOTIFY_EMAIL; never in git, never in a plan comment."
  type        = string
  sensitive   = true
}
