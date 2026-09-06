variable "region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "steakllm"
}

variable "kafka_door_port" {
  description = "The Strimzi loadbalancer listener's port (platform/kafka/kafka.yaml, listener lambda)."
  type        = number
  default     = 9094
}

variable "quarantine_prefix" {
  description = "Where the gateway's presigned uploads land (infra/data's lifecycle rule expires it); the doorbell rule and the Lambda's S3 permissions are scoped to it."
  type        = string
  default     = "quarantine/"
}
