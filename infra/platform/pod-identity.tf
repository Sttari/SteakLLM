# One IAM hat per tenant, handed out by Pod Identity: the association below says "the service account
# <name> in namespace <ns> gets the credentials of this role", and the agent on the node (Step 7's
# add-on) does the handing. No keys, no annotations, no OIDC provider. Each policy names the exact
# resources: Step 10's bucket, table and topic by name, the one Bedrock model, our own secrets.

data "aws_caller_identity" "current" {}

locals {
  account_id  = data.aws_caller_identity.current.account_id
  bucket_arn  = "arn:aws:s3:::${var.documents_bucket}"
  table_arn   = "arn:aws:dynamodb:${var.region}:${local.account_id}:table/${var.catalog_table}"
  topic_arn   = "arn:aws:sns:${var.region}:${local.account_id}:${var.notifications_topic}"
  model_arn   = "arn:aws:bedrock:${var.region}::foundation-model/${var.bedrock_model_id}"
  secrets_arn = "arn:aws:secretsmanager:${var.region}:${local.account_id}:secret:${var.project}/*"

  # service account → { namespace, policy document }
  tenants = {
    external-secrets = { namespace = "external-secrets", policy = data.aws_iam_policy_document.external_secrets.json }
    gateway          = { namespace = "steakllm", policy = data.aws_iam_policy_document.gateway.json }
    embedder         = { namespace = "steakllm", policy = data.aws_iam_policy_document.embedder.json }
    notifier         = { namespace = "steakllm", policy = data.aws_iam_policy_document.notifier.json }
  }
}

data "aws_iam_policy_document" "pod_assume" {
  statement {
    actions = ["sts:AssumeRole", "sts:TagSession"]
    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }
  }
}

# ---- the policies -----------------------------------------------------------------------------------

data "aws_iam_policy_document" "external_secrets" {
  statement {
    sid       = "ReadOurSecrets"
    actions   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    resources = [local.secrets_arn]
  }
}

data "aws_iam_policy_document" "gateway" {
  statement {
    sid       = "ListTheBucket"
    actions   = ["s3:ListBucket"]
    resources = [local.bucket_arn]
  }
  statement {
    sid       = "PresignUploadsReadAndDeleteObjects"
    actions   = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"]
    resources = ["${local.bucket_arn}/quarantine/*", "${local.bucket_arn}/documents/*"]
  }
  statement {
    sid       = "TheCatalog"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:Scan"]
    resources = [local.table_arn]
  }
  statement {
    sid       = "InvokeTheOneModel"
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = [local.model_arn]
  }
}

data "aws_iam_policy_document" "embedder" {
  statement {
    sid       = "ReadDocuments"
    actions   = ["s3:GetObject"]
    resources = ["${local.bucket_arn}/quarantine/*", "${local.bucket_arn}/documents/*"]
  }
  statement {
    sid       = "TheCatalog"
    actions   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
    resources = [local.table_arn]
  }
}

data "aws_iam_policy_document" "notifier" {
  statement {
    sid       = "Publish"
    actions   = ["sns:Publish"]
    resources = [local.topic_arn]
  }
  statement {
    sid       = "TheCatalog"
    actions   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
    resources = [local.table_arn]
  }
}

# ---- roles, policies, associations -------------------------------------------------------------------

resource "aws_iam_role" "tenant" {
  for_each           = local.tenants
  name               = "${var.project}-${each.key}"
  description        = "Pod Identity role for ${each.value.namespace}/${each.key} on the ${var.cluster_name} cluster."
  assume_role_policy = data.aws_iam_policy_document.pod_assume.json
}

resource "aws_iam_role_policy" "tenant" {
  for_each = local.tenants
  name     = "least-privilege"
  role     = aws_iam_role.tenant[each.key].id
  policy   = each.value.policy
}

# The binding. Needs the cluster to exist (apply after eks); recreated by the next apply after a rebuild.
resource "aws_eks_pod_identity_association" "tenant" {
  for_each        = local.tenants
  cluster_name    = var.cluster_name
  namespace       = each.value.namespace
  service_account = each.key
  role_arn        = aws_iam_role.tenant[each.key].arn
}
