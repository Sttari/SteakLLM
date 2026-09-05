terraform {
  backend "s3" {
    bucket       = "steakllm-tfstate-188972e1"
    key          = "data/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
