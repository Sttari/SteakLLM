data "aws_caller_identity" "current" {}

# The network, as infra/network left it. Read-only: the plan role has s3:GetObject on the state bucket.
data "terraform_remote_state" "network" {
  backend = "s3"
  config = {
    bucket = "steakllm-tfstate-188972e1"
    key    = "network/terraform.tfstate"
    region = var.region
  }
}

locals {
  account_id         = data.aws_caller_identity.current.account_id
  private_subnet_ids = data.terraform_remote_state.network.outputs.private_subnet_ids
  apply_role_arn     = "arn:aws:iam::${local.account_id}:role/${var.apply_role_name}"
}
