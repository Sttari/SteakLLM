# Own state key in the shared bucket; the plan role reads it, the apply role writes it.
# infra/eks reads this module's outputs through terraform_remote_state on the same key.
terraform {
  backend "s3" {
    bucket       = "steakllm-tfstate-188972e1"
    key          = "network/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
