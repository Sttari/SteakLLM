# The nightly reaper: a Lambda that shuts down any GPU-pool instance still running at 03:00 UTC.
# It may describe instances and terminate only those tagged as the GPU NodePool — nothing else.

data "archive_file" "reaper" {
  type        = "zip"
  source_file = "${path.module}/lambda/reaper.py"
  output_path = "${path.module}/.build/reaper.zip"
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "reaper" {
  statement {
    sid       = "FindGpuInstances"
    actions   = ["ec2:DescribeInstances"] # Describe* accepts no resource ARN
    resources = ["*"]
  }
  statement {
    sid       = "ShutDownOnlyTheGpuPool"
    actions   = ["ec2:TerminateInstances"]
    resources = ["arn:aws:ec2:${var.region}:${local.account_id}:instance/*"]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/karpenter.sh/nodepool"
      values   = [var.gpu_nodepool]
    }
  }
  statement {
    sid       = "Log"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.reaper.arn}:*"]
  }
}

resource "aws_iam_role" "reaper" {
  name               = "${var.project}-gpu-reaper"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "reaper" {
  name   = "reap-the-gpu-pool"
  role   = aws_iam_role.reaper.id
  policy = data.aws_iam_policy_document.reaper.json
}

resource "aws_cloudwatch_log_group" "reaper" {
  #checkov:skip=CKV_AWS_338:14 days of a nightly one-liner is plenty
  #checkov:skip=CKV_AWS_158:AWS-managed encryption at rest for a log that names instance ids
  name              = "/aws/lambda/${var.project}-gpu-reaper"
  retention_in_days = 14
}

resource "aws_lambda_function" "reaper" {
  #checkov:skip=CKV_AWS_116:No dead-letter queue: it runs every night; a missed run is caught by the next, and Karpenter's expireAfter is the other backstop
  #checkov:skip=CKV_AWS_117:Not in the VPC on purpose: it calls the EC2 API, needs no VPC path, and a VPC Lambda would need the NAT
  #checkov:skip=CKV_AWS_173:Environment variable is a NodePool name, not a secret
  #checkov:skip=CKV_AWS_272:Code signing for a 30-line function the pipeline deploys from git is process for no risk
  #checkov:skip=CKV_AWS_50:X-Ray tracing for a nightly one-call function is noise
  function_name                  = "${var.project}-gpu-reaper"
  role                           = aws_iam_role.reaper.arn
  handler                        = "reaper.handler"
  runtime                        = "python3.12"
  architectures                  = ["arm64"]
  timeout                        = 30
  memory_size                    = 128
  filename                       = data.archive_file.reaper.output_path
  source_code_hash               = data.archive_file.reaper.output_base64sha256
  reserved_concurrent_executions = 1
  environment {
    variables = { GPU_NODEPOOL = var.gpu_nodepool }
  }
  depends_on = [aws_cloudwatch_log_group.reaper]
}

resource "aws_cloudwatch_event_rule" "reaper" {
  name                = "${var.project}-gpu-reaper-nightly"
  schedule_expression = var.reaper_schedule
}

resource "aws_cloudwatch_event_target" "reaper" {
  rule = aws_cloudwatch_event_rule.reaper.name
  arn  = aws_lambda_function.reaper.arn
}

resource "aws_lambda_permission" "reaper" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.reaper.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.reaper.arn
}
