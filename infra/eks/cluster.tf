# The control plane (7.3). AWS runs the API server, scheduler and etcd; we say where (the private
# subnets), who may talk to it (access entries, and one /32 on the public endpoint for now), what it
# logs, and which version. $0.10/hour from `apply` on; it cannot be paused, only torn down.

# ---- the cluster's own role: what the control plane may do in our account ----------------------------

data "aws_iam_policy_document" "cluster_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "cluster" {
  name               = "${var.project}-eks-cluster"
  assume_role_policy = data.aws_iam_policy_document.cluster_assume.json
}

resource "aws_iam_role_policy_attachment" "cluster" {
  role       = aws_iam_role.cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

# ---- control-plane logs: created here so retention is ours, not EKS's default of "forever" ---------

resource "aws_cloudwatch_log_group" "cluster" {
  #checkov:skip=CKV_AWS_338:14 days of control-plane logs, not a year: cents, and enough to debug; a year of audit logs costs real money for no reader
  #checkov:skip=CKV_AWS_158:AWS-managed encryption at rest; a customer KMS key is $1/month for logs nobody but us reads
  name              = "/aws/eks/${var.cluster_name}/cluster"
  retention_in_days = var.log_retention_days
}

# ---- the cluster -----------------------------------------------------------------------------------

resource "aws_eks_cluster" "this" {
  #checkov:skip=CKV_AWS_339:checkov's list of supported versions lags AWS; 1.36 is the default standard-support version (aws eks describe-cluster-versions, Sep 2 2026)
  #checkov:skip=CKV_AWS_58:Secrets are envelope-encrypted with an AWS-owned KMS key by default on current EKS; a customer key adds $1/month and a key to manage for the same guarantee
  name     = var.cluster_name
  version  = var.cluster_version
  role_arn = aws_iam_role.cluster.arn

  access_config {
    authentication_mode                         = "API" # access entries only; no aws-auth ConfigMap to hand-edit
    bootstrap_cluster_creator_admin_permissions = false # the creator (the apply role) gets an explicit entry below
  }

  vpc_config {
    subnet_ids              = local.private_subnet_ids
    endpoint_private_access = true
    endpoint_public_access  = false # the API is reached over the tailnet's subnet router only (8.9, ADR-0010); Step 7's /32 interim is over
  }

  # All five log streams: api, audit and authenticator are the ones we read; the other two are cheap
  # and complete the picture when a pod will not schedule.
  enabled_cluster_log_types = ["api", "audit", "authenticator", "controllerManager", "scheduler"]

  # Standard support only. Extended support (a version older than ~14 months) is $0.60/hour — six
  # times the cluster — and is enrolled silently by default. We upgrade instead.
  upgrade_policy {
    support_type = "STANDARD"
  }

  # No self-managed add-ons on creation: 7.4 installs vpc-cni, coredns, kube-proxy and the rest as
  # managed add-ons, pinned. Nodes cannot join until those exist, which is the order 7.4 enforces.
  bootstrap_self_managed_addons = false

  depends_on = [
    aws_iam_role_policy_attachment.cluster,
    aws_cloudwatch_log_group.cluster,
  ]
}

# ---- who may talk to the API: the guest list -------------------------------------------------------

# The pipeline's apply role: it created the cluster and will manage add-ons and node groups (AWS API),
# and it needs the Kubernetes API for nothing yet — but a creator with no entry cannot even describe
# its own cluster's workloads in the console, and the teardown drill reads state through it.
resource "aws_eks_access_entry" "apply" {
  cluster_name  = aws_eks_cluster.this.name
  principal_arn = local.apply_role_arn
  type          = "STANDARD"
}

resource "aws_eks_access_policy_association" "apply_admin" {
  cluster_name  = aws_eks_cluster.this.name
  principal_arn = aws_eks_access_entry.apply.principal_arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  access_scope {
    type = "cluster"
  }
}

# Thomas's laptop identity: kubectl from the one allowed address, and the Argo bootstrap drill (7.5).
resource "aws_eks_access_entry" "admin" {
  cluster_name  = aws_eks_cluster.this.name
  principal_arn = var.admin_principal_arn
  type          = "STANDARD"
}

resource "aws_eks_access_policy_association" "admin" {
  cluster_name  = aws_eks_cluster.this.name
  principal_arn = aws_eks_access_entry.admin.principal_arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  access_scope {
    type = "cluster"
  }
}

# Karpenter (Step 9) finds the security group its nodes must join by this tag; the subnets carry it
# from infra/network. Only the module that owns the cluster can tag the group EKS created for it.
resource "aws_ec2_tag" "cluster_sg_discovery" {
  resource_id = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
  key         = "karpenter.sh/discovery"
  value       = var.project
}
