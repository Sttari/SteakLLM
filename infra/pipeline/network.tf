data "terraform_remote_state" "network" {
  backend = "s3"
  config = {
    bucket = "steakllm-tfstate-188972e1"
    key    = "network/terraform.tfstate"
    region = var.region
  }
}

data "aws_prefix_list" "s3" {
  name = "com.amazonaws.${var.region}.s3"
}

data "aws_prefix_list" "dynamodb" {
  name = "com.amazonaws.${var.region}.dynamodb"
}
