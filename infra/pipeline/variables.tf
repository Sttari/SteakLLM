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
