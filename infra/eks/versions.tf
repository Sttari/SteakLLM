# infra/eks — the cluster: control plane (7.3), one spot node and the add-ons (7.4). Reads the network's
# outputs from its state. Applied by the pipeline (apply.yml), never the laptop. State key: eks/terraform.tfstate.
# The meter: $0.10/hour for the control plane from the moment this module is applied (ADR-0008).
terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
