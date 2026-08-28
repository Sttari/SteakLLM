provider "aws" {
  region = var.region

  # Every resource this module creates carries these tags; Cost Explorer can split the bill by them.
  default_tags {
    tags = {
      Project   = var.project
      ManagedBy = "terraform"
      Module    = "bootstrap"
    }
  }
}

data "aws_caller_identity" "current" {}
