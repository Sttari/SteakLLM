# infra/bootstrap — the only module ever applied from the laptop.
# Creates what the pipeline cannot create for itself: the Terraform state bucket,
# the GitHub OIDC identity provider and the two CI roles, and the budget alarm.

terraform {
  required_version = ">= 1.10" # S3 backend native locking (use_lockfile) arrived in 1.10

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}
