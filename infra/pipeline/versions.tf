# infra/pipeline — the doorbell (Step 10.3–10.4): the security groups of the Kafka door and the ingest Lambda
# now; the EventBridge rule, the Lambda, its dead-letter queue and role in 10.4. Applied by the pipeline after
# network. State key: pipeline/terraform.tfstate.
terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
