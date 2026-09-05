# The documents bucket: what users upload, what the embedder and summarizer read, what the delete path
# removes. Private, versioned, encrypted with the S3-managed key, TLS-only, and it rings EventBridge on
# every object event (10.4's rule filters them). quarantine/ is where a presigned upload lands; the Lambda
# validates and records it, and anything left there expires after a week.

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "documents" {
  #checkov:skip=CKV_AWS_18:Access logging costs a second bucket; CloudTrail data events are Step 11's audit if needed
  #checkov:skip=CKV_AWS_144:Cross-region replication of re-uploadable documents is money for no resilience gain here
  #checkov:skip=CKV_AWS_145:SSE-S3 (AES256) is the decision; a customer KMS key is Step 11's hardening if the demo needs it
  bucket = "${var.project}-documents-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket                  = aws_s3_bucket.documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    id     = "quarantine-expires"
    status = "Enabled"
    filter {
      prefix = var.quarantine_prefix
    }
    expiration {
      days = var.quarantine_days
    }
  }
  rule {
    id     = "tidy"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
    noncurrent_version_expiration {
      noncurrent_days = 30 # a deleted or re-uploaded document keeps its previous version a month (drill 09 relies on nothing here)
    }
  }
}

# Every object event → EventBridge (the bucket-level switch; the rule that picks created/removed under
# the right prefix lives in infra/pipeline).
resource "aws_s3_bucket_notification" "documents" {
  bucket      = aws_s3_bucket.documents.id
  eventbridge = true
}

data "aws_iam_policy_document" "documents_tls_only" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.documents.arn, "${aws_s3_bucket.documents.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "documents" {
  bucket = aws_s3_bucket.documents.id
  policy = data.aws_iam_policy_document.documents_tls_only.json
}
