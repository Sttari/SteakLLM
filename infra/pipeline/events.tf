# The doorbell wire: S3 → EventBridge (the bucket rings on every object event, 10.2) → this rule picks
# "created or deleted, in the documents bucket, under quarantine/" → the Lambda. Two retries at the
# EventBridge hop, then its dead-letter queue (the Lambda has its own for its own retries).
resource "aws_cloudwatch_event_rule" "ingest" {
  name        = "${var.project}-ingest-doorbell"
  description = "Object Created / Object Deleted under quarantine/ in the documents bucket → the ingest Lambda"
  event_pattern = jsonencode({
    source        = ["aws.s3"]
    "detail-type" = ["Object Created", "Object Deleted"]
    detail = {
      bucket = { name = [local.documents_bucket] }
      object = { key = [{ prefix = var.quarantine_prefix }] }
    }
  })
}

resource "aws_cloudwatch_event_target" "ingest" {
  rule = aws_cloudwatch_event_rule.ingest.name
  arn  = aws_lambda_function.ingest.arn
  retry_policy {
    maximum_retry_attempts       = 2
    maximum_event_age_in_seconds = 3600
  }
  dead_letter_config {
    arn = aws_sqs_queue.ingest_dlq.arn
  }
}

resource "aws_lambda_permission" "ingest" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingest.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ingest.arn
}
