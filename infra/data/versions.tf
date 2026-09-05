# infra/data — the pipeline's durable state (Step 10.2): the documents bucket, the catalog table and the
# notifications topic. Applied by the pipeline; independent of the cluster (nothing here needs eks), so it
# survives cluster teardowns by design: documents, catalog rows and the subscription are the point.
# State key: data/terraform.tfstate.
terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
