# The notifier's watch-list (10.1c amended in 10.4: its own small table, not the catalog). Items are
# { term }: `aws dynamodb put-item --table-name steakllm-watchlist --item '{"term":{"S":"gpu"}}'`.
# The notifier reads it once at start; a rollout reloads it.
resource "aws_dynamodb_table" "watchlist" {
  #checkov:skip=CKV_AWS_119:Encrypted at rest with the AWS-owned key; the items are a handful of words
  #checkov:skip=CKV_AWS_28:No point-in-time recovery for a two-item list that git and the field notes also hold
  name         = "${var.project}-watchlist"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "term"

  attribute {
    name = "term"
    type = "S"
  }
}
