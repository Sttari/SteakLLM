# GitHub Actions identity, without stored keys.
# GitHub signs a short-lived token saying "this job runs from <owner>/<repo> on <ref>";
# AWS trusts GitHub's OIDC issuer and lends the job a role for the length of the job.
# Two roles: plan (read-only, any branch or pull request) and apply (main branch or the production environment only).

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # AWS validates GitHub's certificate against its own trust store since 2023; the thumbprint is required by the API but not relied on.
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

locals {
  repo_sub_prefix = "repo:${var.github_owner}/${var.github_repo}"
}

# ---- plan role: read everything, write nothing except the state lock ----

data "aws_iam_policy_document" "plan_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    # Any ref in this repository: branches and pull requests may plan.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["${local.repo_sub_prefix}:*"]
    }
  }
}

resource "aws_iam_role" "ci_plan" {
  name                 = "${var.project}-ci-plan"
  description          = "GitHub Actions: terraform plan on pull requests (read-only + state lock)."
  assume_role_policy   = data.aws_iam_policy_document.plan_trust.json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "ci_plan_readonly" {
  role       = aws_iam_role.ci_plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

# `terraform plan` reads state and takes the lock; the lock is an object named <key>.tflock.
data "aws_iam_policy_document" "plan_state" {
  statement {
    sid       = "ListStateBucket"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.tfstate.arn]
  }
  statement {
    sid       = "ReadState"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.tfstate.arn}/*"]
  }
  statement {
    sid       = "TakeAndReleaseLock"
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.tfstate.arn}/*.tflock"]
  }
}

resource "aws_iam_role_policy" "ci_plan_state" {
  name   = "terraform-state-read-and-lock"
  role   = aws_iam_role.ci_plan.id
  policy = data.aws_iam_policy_document.plan_state.json
}

# ---- apply role: main branch or the production environment only ----

data "aws_iam_policy_document" "apply_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    # Jobs that reference a GitHub Environment present `environment:<name>` as their subject; plain main-branch jobs present the ref.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "${local.repo_sub_prefix}:ref:refs/heads/main",
        "${local.repo_sub_prefix}:environment:production",
      ]
    }
  }
}

resource "aws_iam_role" "ci_apply" {
  name                 = "${var.project}-ci-apply"
  description          = "GitHub Actions: terraform apply from main (see ADR-0001 for the scoping plan)."
  assume_role_policy   = data.aws_iam_policy_document.apply_trust.json
  max_session_duration = 3600
}

# Broad on purpose while the platform is being built (VPC, EKS, IAM roles for pods, Lambda, budgets…).
# ADR-0001 records the plan to narrow it with IAM Access Analyzer's policy generation once the resource set is known.
resource "aws_iam_role_policy_attachment" "ci_apply_admin" {
  role       = aws_iam_role.ci_apply.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}
