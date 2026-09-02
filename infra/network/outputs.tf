output "vpc_id" {
  description = "The VPC; infra/eks reads it through terraform_remote_state."
  value       = aws_vpc.this.id
}

output "vpc_cidr" {
  description = "The VPC's range; security groups that admit 'the VPC' use it."
  value       = aws_vpc.this.cidr_block
}

output "public_subnet_ids" {
  description = "Load balancer and NAT subnets, one per AZ, in var.azs order."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Node and pod subnets, one per AZ, in var.azs order. infra/eks puts the node group in the first (EBS volumes are AZ-bound; ADR-0008)."
  value       = aws_subnet.private[*].id
}

output "azs" {
  description = "The availability zones, in the same order as the subnet lists."
  value       = var.azs
}

output "nat_public_ip" {
  description = "The Elastic IP every outbound packet from the private subnets appears to come from. The egress drill (7.4) expects to see it."
  value       = aws_eip.nat.public_ip
}

output "nat_eni_id" {
  description = "The static network interface the private route table points at; the NAT instance attaches to it on boot."
  value       = aws_network_interface.nat.id
}

output "nat_instance_id" {
  description = "The NAT instance; `aws ssm start-session --target <id>` is the only way onto it."
  value       = aws_instance.nat.id
}
