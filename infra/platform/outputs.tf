output "secret_names" {
  description = "The three Secrets Manager names a human fills: aws secretsmanager put-secret-value --secret-id <name> --secret-string '…' (in a terminal, never in git)."
  value       = { for k, s in aws_secretsmanager_secret.this : k => s.name }
}

output "tenant_role_arns" {
  description = "service account → role ARN; the Helm charts' ServiceAccounts need no annotation (Pod Identity binds by name), this is for the record."
  value       = { for k, r in aws_iam_role.tenant : k => r.arn }
}

output "pod_identity_associations" {
  description = "namespace/service-account pairs bound on the cluster."
  value       = [for k, a in aws_eks_pod_identity_association.tenant : "${a.namespace}/${a.service_account}"]
}
