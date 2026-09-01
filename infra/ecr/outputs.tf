output "repository_urls" {
  description = "service name → repository URL; release.yml pushes here and the Helm values reference it."
  value       = { for k, r in aws_ecr_repository.service : k => r.repository_url }
}
