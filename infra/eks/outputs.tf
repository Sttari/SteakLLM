output "cluster_name" {
  description = "For `aws eks update-kubeconfig --name`."
  value       = aws_eks_cluster.this.name
}

output "cluster_version" {
  description = "The running Kubernetes version."
  value       = aws_eks_cluster.this.version
}

output "cluster_endpoint" {
  description = "The API server URL (reachable privately from the VPC, and publicly from admin_cidr only)."
  value       = aws_eks_cluster.this.endpoint
}

output "cluster_security_group_id" {
  description = "The security group EKS created for control-plane ↔ node traffic; Step 8's stateful charts and Step 9's Karpenter reference it."
  value       = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
}

output "private_subnet_ids" {
  description = "Passed through from infra/network for the node group (7.4) and Karpenter (Step 9)."
  value       = local.private_subnet_ids
}

output "node_role_arn" {
  description = "The node role; Step 9's Karpenter nodes reuse it."
  value       = aws_iam_role.node.arn
}

output "node_group_name" {
  description = "The always-on CPU node group."
  value       = aws_eks_node_group.cpu.node_group_name
}
