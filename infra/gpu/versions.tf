# infra/gpu — the AWS side of the GPU pool (Step 9.2): the models bucket, the mirrored vLLM image's
# repository, Karpenter's controller role and interruption queue, the mirror and vLLM Pod Identity roles,
# and the nightly reaper. Applied by the pipeline after eks and platform (the associations need the cluster).
# State key: gpu/terraform.tfstate. Survives cluster teardowns: the bucket and the image are the point.
terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}
