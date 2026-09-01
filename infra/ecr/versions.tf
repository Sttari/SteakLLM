# infra/ecr — image repositories for the five services. Applied by the pipeline (apply.yml), never the laptop.
terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
