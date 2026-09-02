output "account_id" {
  description = "AWS account the bootstrap ran in."
  value       = data.aws_caller_identity.current.account_id
}

output "tfstate_bucket" {
  description = "State bucket name; goes into every module's backend block and into the CI variables."
  value       = aws_s3_bucket.tfstate.bucket
}

output "oidc_provider_arn" {
  description = "GitHub OIDC identity provider."
  value       = aws_iam_openid_connect_provider.github.arn
}

output "ci_plan_role_arn" {
  description = "Role GitHub Actions assumes on pull requests (read-only + state lock). Store as repo variable AWS_PLAN_ROLE_ARN."
  value       = aws_iam_role.ci_plan.arn
}

output "ci_apply_role_arn" {
  description = "Role GitHub Actions assumes on main / the production environment. Store as repo variable AWS_APPLY_ROLE_ARN."
  value       = aws_iam_role.ci_apply.arn
}

output "ci_release_role_arn" {
  description = "Role release.yml assumes from main: ECR push to steakllm/* and nothing else. Stored as the GitHub variable AWS_RELEASE_ROLE_ARN."
  value       = aws_iam_role.ci_release.arn
}
