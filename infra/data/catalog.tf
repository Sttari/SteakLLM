# The catalog: the row every service already addresses by `doc_id` (ingest writes it, the embedder,
# summarizer and notifier update it, the gateway reads and deletes it — Step 6's contract). One hash
# key, no sort key: the code is the schema. On-demand billing (pennies at our volume), point-in-time
# recovery (drill 10 restores from it), deletion protection (drill 10 turns it off on purpose, then
# back on). The notifier's watch-list gets its own small table in 10.5 (10.1c amended: five services
# would have changed for a two-item list).
resource "aws_dynamodb_table" "catalog" {
  #checkov:skip=CKV_AWS_119:Encrypted at rest with the AWS-owned key; a customer KMS key is $1/month for a catalog of file names
  name                        = "${var.project}-catalog"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "doc_id"
  deletion_protection_enabled = true

  attribute {
    name = "doc_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}
