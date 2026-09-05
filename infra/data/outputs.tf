output "documents_bucket" {
  value = aws_s3_bucket.documents.bucket
}

output "catalog_table" {
  value = aws_dynamodb_table.catalog.name
}

output "notifications_topic_arn" {
  value = aws_sns_topic.notifications.arn
}
