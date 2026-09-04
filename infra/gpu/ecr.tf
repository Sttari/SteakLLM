# The mirrored vLLM image, in-region: a cold start pulls ≈ 10 GB from ECR, never from Docker Hub through the NAT.
resource "aws_ecr_repository" "vllm" {
  #checkov:skip=CKV_AWS_136:AES256 default encryption; a KMS key adds cost for a public image
  name                 = var.vllm_image_repository
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  image_scanning_configuration {
    scan_on_push = true
  }
  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "vllm" {
  repository = aws_ecr_repository.vllm.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "keep the last 3 mirrored versions"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 3 }
      action       = { type = "expire" }
    }]
  })
}
