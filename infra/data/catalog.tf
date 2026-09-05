# The catalog: one table, two keys, many shapes (ADR-0012). doc#<doc_id> rows carry status
# (uploaded → indexed → summarized → deleted) and metadata; watch#<term> rows are the notifier's
# watch-list. On-demand billing (pennies at our volume), point-in-time recovery (drill 10 restores from
# it), deletion protection (drill 10 turns it off on purpose, then back on).
resource "aws_dynamodb_table" "catalog" {
  #checkov:skip=CKV_AWS_119:Encrypted at rest with the AWS-owned key; a customer KMS key is $1/month for a catalog of file names
  name                        = "${var.project}-catalog"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "pk"
  range_key                   = "sk"
  deletion_protection_enabled = true

  attribute {
    name = "pk"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}
