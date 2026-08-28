# Where this module's state lives, and how it's locked. Created in Step 2.5 after the bucket existed.
terraform {
  backend "s3" {
    bucket       = "steakllm-tfstate-188972e1"
    key          = "bootstrap/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
