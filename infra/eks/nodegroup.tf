# The one body (7.4): a managed node group of one node bought as spot (ADR-0008; t4g.xlarge since 8.1, ADR-0009). AWS launches,
# replaces and upgrades the node; we say what it is, where it lives and what it may do.

# ---- the node's role: join the cluster, pull images, give pods addresses, be reachable by SSM ---------

data "aws_iam_policy_document" "node_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "node" {
  name               = "${var.project}-eks-node"
  assume_role_policy = data.aws_iam_policy_document.node_assume.json
}

resource "aws_iam_role_policy_attachment" "node" {
  for_each = toset([
    "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",          # join and describe the cluster
    "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPullOnly", # pull our five images from ECR
    "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",               # the VPC CNI assigns pod addresses from the node
    "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",       # Session Manager, no SSH (as the NAT)
  ])
  role       = aws_iam_role.node.name
  policy_arn = each.value
}

# ---- the launch template: disk, metadata, nothing else (EKS supplies the AMI and the bootstrap) ------

resource "aws_launch_template" "cpu" {
  name_prefix = "${var.project}-cpu-"
  # No image_id: the managed node group picks the EKS-optimized AL2023 arm64 AMI for the cluster version
  # and rolls it forward on upgrade. No user_data: AL2023 nodes bootstrap through nodeadm from EKS.
  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = 40 # images (five of ours ≈ 100 MiB each, Ollama's 7 GB), logs, ephemeral storage
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }
  metadata_options {
    http_tokens                 = "required" # IMDSv2 only
    http_put_response_hop_limit = 1          # pods cannot reach the node's credentials; they get their own (Pod Identity)
  }
  monitoring {
    enabled = false # detailed monitoring is $2.10/month per instance; kube-prometheus-stack (Step 8) watches the node
  }
  tag_specifications {
    resource_type = "instance"
    tags          = { Name = "${var.project}-cpu", "steakllm.io/pool" = "cpu" }
  }
  tag_specifications {
    resource_type = "volume"
    tags          = { Name = "${var.project}-cpu-root" }
  }
  update_default_version = true
}

# ---- the node group -------------------------------------------------------------------------------

resource "aws_eks_node_group" "cpu" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = "cpu"
  node_role_arn   = aws_iam_role.node.arn
  # One AZ only: Step 8's EBS volumes (Kafka, Qdrant, Prometheus) are AZ-bound; a replacement node
  # in the other AZ could not mount them (ADR-0008).
  subnet_ids     = [local.private_subnet_ids[0]]
  ami_type       = "AL2023_ARM_64_STANDARD"
  capacity_type  = "SPOT" # xlarge ≈ $0.071/hour on Sep 3 2026 against $0.134 on-demand; reclaimed with 2 minutes' notice, replaced by the group
  instance_types = [var.node_instance_type]
  labels         = { "steakllm.io/pool" = "cpu" }

  scaling_config {
    desired_size = 1
    min_size     = 1
    max_size     = 2 # room for a rolling replacement, never a second permanent node
  }

  update_config {
    max_unavailable = 1
  }

  launch_template {
    id      = aws_launch_template.cpu.id
    version = aws_launch_template.cpu.latest_version
  }

  # Nodes cannot join without the networking add-ons (the cluster was created with none).
  depends_on = [
    aws_iam_role_policy_attachment.node,
    aws_eks_addon.vpc_cni,
    aws_eks_addon.kube_proxy,
    aws_eks_addon.pod_identity_agent,
  ]

  lifecycle {
    ignore_changes = [scaling_config[0].desired_size] # a replacement in flight may briefly read 2; not drift
  }
}
