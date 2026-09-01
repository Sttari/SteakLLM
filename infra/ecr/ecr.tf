# One repository per service. Images are tagged with the git SHA by release.yml (Step 6).
resource "aws_ecr_repository" "service" {
  for_each = toset(var.services)

  #checkov:skip=CKV_AWS_136:AES256 (SSE) is sufficient for images built from a public repo; KMS adds cost and key management for no threat-model gain
  name                 = "${var.project}/${each.key}"
  image_tag_mutability = "IMMUTABLE" # a tag can never be silently re-pointed: what was scanned is what deploys
  force_delete         = false       # refuse to delete a repository that still holds images

  image_scanning_configuration {
    scan_on_push = true # basic CVE scan on every push; free
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

# Storage is the only billable part of ECR (~$0.10/GB-month). Keep it bounded:
# untagged layers (from failed or superseded builds) go after 7 days; only the last 10 images stay.
resource "aws_ecr_lifecycle_policy" "service" {
  for_each   = aws_ecr_repository.service
  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "expire untagged images after 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "keep only the last 10 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = { type = "expire" }
      }
    ]
  })
}
