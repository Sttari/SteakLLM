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

# GitHub presents the subject in one of two shapes: the classic name form, or the immutable form that
# pins numeric IDs to the names (repo:Sttari@43324946/SteakLLM@1350070618:…). This repo gets the immutable
# form (CloudTrail, Aug 28 2026); the trust accepts both, and the ID form is the stronger one: a repo
# deleted and re-created under the same name gets a new ID and cannot inherit the role.
locals {
  repo_sub_prefixes = [
    "repo:${var.github_owner}/${var.github_repo}",
    "repo:${var.github_owner}@${var.github_owner_id}/${var.github_repo}@${var.github_repo_id}",
  ]
  apply_subjects = flatten([
    for p in local.repo_sub_prefixes : ["${p}:ref:refs/heads/main", "${p}:environment:production"]
  ])
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
      values   = [for p in local.repo_sub_prefixes : "${p}:*"]
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
  # The end-to-end test in CI runs the real gateway and summarizer, which call Bedrock. One model,
  # invoke only, no management; pennies per run (Step 6.10).
  statement {
    sid       = "InvokeTheOneModel"
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = ["arn:aws:bedrock:${var.region}::foundation-model/${var.bedrock_model_id}"]
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
      values   = local.apply_subjects
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
  #checkov:skip=CKV_AWS_274:Broad on purpose while the platform is being built; ADR-0001 records the narrowing plan
  role       = aws_iam_role.ci_apply.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

# ---- release role: push images from main, and nothing else ----
# release.yml builds the five service images and pushes them to ECR. Narrower than apply on purpose
# (ADR-0001, amended Sep 2 2026): a job that only ships images should hold only that. It may push to
# and read the ${project}/* repositories; it cannot create, delete or reconfigure anything.

data "aws_iam_policy_document" "release_trust" {
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
    # main only: no pull request, no other branch, no environment can release.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [for p in local.repo_sub_prefixes : "${p}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "ci_release" {
  name                 = "${var.project}-ci-release"
  description          = "GitHub Actions: push service images to ECR from main (release.yml); ECR push only."
  assume_role_policy   = data.aws_iam_policy_document.release_trust.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "release_ecr" {
  statement {
    sid     = "LogInToTheRegistry"
    actions = ["ecr:GetAuthorizationToken"] # `docker login`; this action accepts no resource narrower than *
    #checkov:skip=CKV_AWS_356:GetAuthorizationToken is not resource-scopable; every other action below is scoped to steakllm/*
    resources = ["*"]
  }
  statement {
    sid = "PushToAndReadOurRepositories"
    actions = [
      "ecr:BatchCheckLayerAvailability", # push: which layers are already there
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage",
      "ecr:BatchGetImage",             # buildx reads existing manifests when it assembles the arm64+amd64 list
      "ecr:GetDownloadUrlForLayer",    # … and existing layers for the cache
      "ecr:DescribeImages",            # "already released?" — tags are immutable, so a re-run must look first
      "ecr:DescribeImageScanFindings", # the scan-on-push verdict for the run summary
    ]
    # The repositories live in infra/ecr (a separate state); the prefix, not a data source, keeps
    # bootstrap free of a dependency on a module it is applied before.
    resources = ["arn:aws:ecr:${var.region}:${data.aws_caller_identity.current.account_id}:repository/${var.project}/*"]
  }
}

resource "aws_iam_role_policy" "ci_release_ecr" {
  name   = "ecr-push-only"
  role   = aws_iam_role.ci_release.id
  policy = data.aws_iam_policy_document.release_ecr.json
}
