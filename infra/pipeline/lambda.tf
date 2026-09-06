# The doorbell (ADR-0012): validate · hash · record · produce. A container image (the lambda stage of
# services/ingest/Dockerfile), arm64, in the private subnets with the ingest-lambda security group: it
# reaches S3 and DynamoDB through the gateway endpoints and Kafka through the door, and nothing else.

variable "ingest_image_tag" {
  description = "steakllm/ingest image tag of the Lambda flavour (release.yml pushes lambda-sha-<7>)."
  type        = string
  default     = "lambda-sha-e57f114"
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

data "aws_iam_policy_document" "ingest" {
  statement {
    sid       = "ReadTheUpload"
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${local.bucket_arn}/*"]
  }
  statement {
    sid       = "MoveARejection"
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["${local.bucket_arn}/rejected/*", "${local.bucket_arn}/${var.quarantine_prefix}*"]
  }
  statement {
    sid       = "ListForTheCopy"
    actions   = ["s3:ListBucket"]
    resources = [local.bucket_arn]
  }
  statement {
    sid       = "RecordTheDocument"
    actions   = ["dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:GetItem", "dynamodb:Scan"]
    resources = [local.table_arn]
  }
  statement {
    sid       = "ReadTheClusterCA"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.kafka_ca.arn]
  }
  statement {
    sid       = "Park"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.ingest_dlq.arn]
  }
  statement {
    sid       = "Log"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.ingest.arn}:*"]
  }
}

resource "aws_iam_role" "ingest" {
  name               = "${var.project}-ingest"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "ingest" {
  name   = "doorbell"
  role   = aws_iam_role.ingest.id
  policy = data.aws_iam_policy_document.ingest.json
}

# The ENI verbs a VPC Lambda needs (CreateNetworkInterface & co.), AWS's own policy.
resource "aws_iam_role_policy_attachment" "ingest_vpc" {
  role       = aws_iam_role.ingest.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_cloudwatch_log_group" "ingest" {
  #checkov:skip=CKV_AWS_338:14 days: the field notes and Loki (Step 11 ships these there) are the record
  #checkov:skip=CKV_AWS_158:AWS-managed encryption at rest; the log carries object keys and doc ids, not content
  name              = "/aws/lambda/${var.project}-ingest"
  retention_in_days = 14
}

resource "aws_lambda_function" "ingest" {
  #checkov:skip=CKV_AWS_173:Environment variables are names and addresses; the CA is fetched from Secrets Manager at start
  #checkov:skip=CKV_AWS_272:Code signing for an image the pipeline builds from git and Trivy scans is process for no risk
  #checkov:skip=CKV_AWS_50:X-Ray tracing arrives with Step 11's tracing decision, not here
  #checkov:skip=CKV_AWS_115:No reserved concurrency: this account's Lambda limit is below the unreserved minimum (Incident 34a)
  function_name = "${var.project}-ingest"
  role          = aws_iam_role.ingest.arn
  package_type  = "Image"
  image_uri     = "${local.account_id}.dkr.ecr.${var.region}.amazonaws.com/steakllm/ingest:${var.ingest_image_tag}"
  architectures = ["arm64"]
  timeout       = 60
  memory_size   = 512

  vpc_config {
    subnet_ids         = data.terraform_remote_state.network.outputs.private_subnet_ids
    security_group_ids = [aws_security_group.ingest_lambda.id]
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.ingest_dlq.arn
  }

  environment {
    variables = {
      DOCUMENTS_BUCKET        = local.documents_bucket
      CATALOG_TABLE           = local.catalog_table
      QUARANTINE_PREFIX       = var.quarantine_prefix
      KAFKA_BOOTSTRAP         = local.kafka_bootstrap
      KAFKA_SECURITY_PROTOCOL = "SSL"
      KAFKA_CA_SECRET_ID      = aws_secretsmanager_secret.kafka_ca.name
      TOPIC_DOCUMENTS         = "documents"
      LOG_LEVEL               = "INFO"
    }
  }

  depends_on = [aws_cloudwatch_log_group.ingest, aws_iam_role_policy_attachment.ingest_vpc]
}

# Async invocations (EventBridge's kind): two retries, then the dead-letter queue above.
resource "aws_lambda_function_event_invoke_config" "ingest" {
  function_name                = aws_lambda_function.ingest.function_name
  maximum_retry_attempts       = 2
  maximum_event_age_in_seconds = 3600
}
