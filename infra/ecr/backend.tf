# Own state key in the shared bucket; the plan role reads it, the apply role writes it.
terraform {
  backend "s3" {
    bucket       = "steakllm-tfstate-188972e1"
    key          = "ecr/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
