# Two more Pod Identity hats: the mirror Jobs (write weights to the bucket, push the image to ECR) and
# vLLM itself (read the weights). Both in the steakllm namespace.

data "aws_iam_policy_document" "mirror" {
  statement {
    sid       = "ListTheBucket"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.models.arn]
  }
  statement {
    sid       = "WriteWeights"
    actions   = ["s3:PutObject", "s3:GetObject", "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"]
    resources = ["${aws_s3_bucket.models.arn}/*"]
  }
  statement {
    sid       = "LogInToTheRegistry"
    actions   = ["ecr:GetAuthorizationToken"] # accepts no narrower resource
    resources = ["*"]
  }
  statement {
    sid = "PushTheImage"
    actions = [
      "ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload",
      "ecr:PutImage", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:DescribeImages",
    ]
    resources = [aws_ecr_repository.vllm.arn]
  }
}

data "aws_iam_policy_document" "vllm" {
  statement {
    sid       = "ListTheBucket"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.models.arn]
  }
  statement {
    sid       = "ReadWeights"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.models.arn}/*"]
  }
}

locals {
  gpu_tenants = {
    mirror = data.aws_iam_policy_document.mirror.json
    vllm   = data.aws_iam_policy_document.vllm.json
  }
}

resource "aws_iam_role" "gpu_tenant" {
  for_each           = local.gpu_tenants
  name               = "${var.project}-${each.key}"
  description        = "Pod Identity role for steakllm/${each.key} on the ${var.cluster_name} cluster (GPU pool)."
  assume_role_policy = data.aws_iam_policy_document.pod_assume.json
}

resource "aws_iam_role_policy" "gpu_tenant" {
  #checkov:skip=CKV_AWS_356:ecr:GetAuthorizationToken (mirror) is not resource-scopable; everything else is scoped
  for_each = local.gpu_tenants
  name     = "least-privilege"
  role     = aws_iam_role.gpu_tenant[each.key].id
  policy   = each.value
}

resource "aws_eks_pod_identity_association" "gpu_tenant" {
  for_each        = local.gpu_tenants
  cluster_name    = var.cluster_name
  namespace       = "steakllm"
  service_account = each.key
  role_arn        = aws_iam_role.gpu_tenant[each.key].arn
}
