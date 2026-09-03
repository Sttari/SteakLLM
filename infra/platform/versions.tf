# infra/platform — what the cluster's tenants need from AWS: Secrets Manager slots (filled by a human,
# never by git) and the IAM roles each service wears through Pod Identity, with their associations.
# Applied by the pipeline after eks (the associations need the cluster to exist). State key: platform/terraform.tfstate.
# Deliberately no remote-state read of eks: that state is empty whenever the cluster is down (dev-time
# posture), and a plan on a pull request must still succeed. The cluster name is a variable.
terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
