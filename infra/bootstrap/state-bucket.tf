# Terraform's memory. Versioned (every state ever written is recoverable), encrypted,
# never public, and locked with S3's native lockfile — no DynamoDB table needed since Terraform 1.10.

# A random suffix keeps the bucket name globally unique without putting the account ID in git.
resource "random_id" "state_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "tfstate" {
  # Findings we chose not to "fix" — each is a decision, on the record (see also ADR-0002):
  #checkov:skip=CKV_AWS_144:One region on purpose; versioning is the recovery story for state, replication is DR overkill
  #checkov:skip=CKV_AWS_145:SSE-S3 (AES256) is sufficient for state; KMS adds cost and key management for no threat-model gain
  #checkov:skip=CKV_AWS_18:Access logging needs a second bucket; CloudTrail already records who touches state
  #checkov:skip=CKV2_AWS_62:No consumer for bucket events; nothing should react to state writes
  bucket = "${var.project}-tfstate-${random_id.state_suffix.hex}"

  # Refuse to delete the bucket while it holds objects; destroying state by accident must be hard.
  force_destroy = false

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket                  = aws_s3_bucket.tfstate.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Keep old state versions for 90 days, then let them go; the current version is never expired.
resource "aws_s3_bucket_lifecycle_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"
    filter {
      prefix = ""
    }
    noncurrent_version_expiration {
      noncurrent_days = 90
    }
    # A multipart upload that dies halfway leaves invisible, billable fragments; sweep them weekly. (CKV_AWS_300)
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}
