# The cluster's own plumbing (7.4), as managed add-ons pinned to the defaults AWS reports for 1.36
# (`aws eks describe-addon-versions --kubernetes-version 1.36`, Sep 3 2026). Bumped on purpose with
# the cluster version, never floated. Two orders matter: networking before the node (or it cannot
# join), and everything that runs as a pod after the node (or the add-on waits for a node that is
# waiting for it).

locals {
  addon_versions = {
    vpc-cni                = "v1.22.4-eksbuild.3"
    kube-proxy             = "v1.36.0-eksbuild.17"
    eks-pod-identity-agent = "v1.3.10-eksbuild.3"
    coredns                = "v1.14.3-eksbuild.14"
    metrics-server         = "v0.9.0-eksbuild.8"
    aws-ebs-csi-driver     = "v1.65.0-eksbuild.1"
  }
}

# ---- before the node: pod networking, service routing, the identity agent -------------------------

resource "aws_eks_addon" "vpc_cni" {
  cluster_name                = aws_eks_cluster.this.name
  addon_name                  = "vpc-cni"
  addon_version               = local.addon_versions["vpc-cni"]
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"
}

resource "aws_eks_addon" "kube_proxy" {
  cluster_name                = aws_eks_cluster.this.name
  addon_name                  = "kube-proxy"
  addon_version               = local.addon_versions["kube-proxy"]
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"
}

# Pod Identity: the agent on each node hands pods the credentials of the role their service account
# is associated with. No OIDC provider, no annotations with role ARNs, no keys.
resource "aws_eks_addon" "pod_identity_agent" {
  cluster_name                = aws_eks_cluster.this.name
  addon_name                  = "eks-pod-identity-agent"
  addon_version               = local.addon_versions["eks-pod-identity-agent"]
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"
}

# ---- after the node: DNS, metrics, storage ---------------------------------------------------------

resource "aws_eks_addon" "coredns" {
  cluster_name                = aws_eks_cluster.this.name
  addon_name                  = "coredns"
  addon_version               = local.addon_versions["coredns"]
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"
  depends_on                  = [aws_eks_node_group.cpu]
}

resource "aws_eks_addon" "metrics_server" {
  cluster_name                = aws_eks_cluster.this.name
  addon_name                  = "metrics-server"
  addon_version               = local.addon_versions["metrics-server"]
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"
  depends_on                  = [aws_eks_node_group.cpu]
}

# The EBS CSI driver: the first pod to wear its own IAM hat. Its controller's service account is
# associated with a role that may create, attach and delete volumes — and nothing else on the node can.
data "aws_iam_policy_document" "ebs_csi_assume" {
  statement {
    actions = ["sts:AssumeRole", "sts:TagSession"] # Pod Identity tags the session with cluster/namespace/service-account
    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ebs_csi" {
  name               = "${var.project}-ebs-csi"
  assume_role_policy = data.aws_iam_policy_document.ebs_csi_assume.json
}

resource "aws_iam_role_policy_attachment" "ebs_csi" {
  role       = aws_iam_role.ebs_csi.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}

resource "aws_eks_addon" "ebs_csi" {
  cluster_name                = aws_eks_cluster.this.name
  addon_name                  = "aws-ebs-csi-driver"
  addon_version               = local.addon_versions["aws-ebs-csi-driver"]
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"
  pod_identity_association {
    role_arn        = aws_iam_role.ebs_csi.arn
    service_account = "ebs-csi-controller-sa"
  }
  depends_on = [aws_eks_node_group.cpu, aws_iam_role_policy_attachment.ebs_csi, aws_eks_addon.pod_identity_agent]
}
