# The models bucket: the weights live here, in our account, and reach the GPU node over the free S3
# gateway endpoint on every cold start. Private, versioned, encrypted with the S3-managed key.

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "models" {
  #checkov:skip=CKV_AWS_18:Access logging on a bucket only our own pods read costs a second bucket for nothing
  #checkov:skip=CKV_AWS_144:Cross-region replication of re-downloadable weights is money for no resilience gain
  #checkov:skip=CKV_AWS_145:SSE-S3 (AES256): a customer KMS key adds $1/month and a key for public weights
  #checkov:skip=CKV2_AWS_62:No event notifications: nothing reacts to a weight upload
  bucket = "${var.project}-models-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "models" {
  bucket                  = aws_s3_bucket.models.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "models" {
  bucket = aws_s3_bucket.models.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "models" {
  bucket = aws_s3_bucket.models.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "models" {
  bucket = aws_s3_bucket.models.id
  rule {
    id     = "tidy"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 7 # a mirror Job that died mid-upload must not leave paid-for parts behind
    }
    noncurrent_version_expiration {
      noncurrent_days = 30 # a re-mirrored model keeps its previous version a month, then goes
    }
  }
}
