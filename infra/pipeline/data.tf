data "terraform_remote_state" "data" {
  backend = "s3"
  config = {
    bucket = "steakllm-tfstate-188972e1"
    key    = "data/terraform.tfstate"
    region = var.region
  }
}

data "aws_caller_identity" "current" {}

# The Kafka door's bootstrap NLB, found by the tags the AWS Load Balancer Controller puts on it. The
# name changes when the Service is recreated (a cluster rebuild); cluster-up's apply re-reads it, so
# the Lambda's environment follows. A private DNS name for it is Step 11's tidy-up.
data "aws_lb" "kafka_door" {
  tags = {
    "service.k8s.aws/stack" = "kafka/steakllm-kafka-lambda-bootstrap"
  }
}

locals {
  account_id       = data.aws_caller_identity.current.account_id
  documents_bucket = data.terraform_remote_state.data.outputs.documents_bucket
  catalog_table    = data.terraform_remote_state.data.outputs.catalog_table
  topic_arn        = data.terraform_remote_state.data.outputs.notifications_topic_arn
  bucket_arn       = "arn:aws:s3:::${local.documents_bucket}"
  table_arn        = "arn:aws:dynamodb:${var.region}:${local.account_id}:table/${local.catalog_table}"
  kafka_bootstrap  = "${data.aws_lb.kafka_door.dns_name}:${var.kafka_door_port}"
}
