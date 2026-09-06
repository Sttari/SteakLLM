data "terraform_remote_state" "data" {
  backend = "s3"
  config = {
    bucket = "steakllm-tfstate-188972e1"
    key    = "data/terraform.tfstate"
    region = var.region
  }
}

data "aws_caller_identity" "current" {}

# The Kafka door's bootstrap NLB is created by the AWS Load Balancer Controller and renamed on every
# cluster rebuild; a Terraform data lookup here made cluster-up fail whenever the cluster was down
# (Incident 47). The Lambda finds it at start by the controller's tag instead (KAFKA_BOOTSTRAP_LOOKUP_TAG).

locals {
  account_id       = data.aws_caller_identity.current.account_id
  documents_bucket = data.terraform_remote_state.data.outputs.documents_bucket
  catalog_table    = data.terraform_remote_state.data.outputs.catalog_table
  topic_arn        = data.terraform_remote_state.data.outputs.notifications_topic_arn
  bucket_arn       = "arn:aws:s3:::${local.documents_bucket}"
  table_arn        = "arn:aws:dynamodb:${var.region}:${local.account_id}:table/${local.catalog_table}"
  kafka_door_tag   = "kafka/steakllm-kafka-lambda-bootstrap" # service.k8s.aws/stack on the bootstrap NLB
}
