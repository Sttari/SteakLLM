# Failures park, they do not vanish (ADR-0012): after the Lambda's own two async retries, the event
# goes here; EventBridge's own delivery failures too. Fourteen days to notice, one alarm to the topic.
resource "aws_sqs_queue" "ingest_dlq" {
  name                      = "${var.project}-ingest-dlq"
  message_retention_seconds = 1209600 # 14 days
  sqs_managed_sse_enabled   = true
}

data "aws_iam_policy_document" "ingest_dlq" {
  statement {
    sid       = "EventBridgeAndLambdaMayPark"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.ingest_dlq.arn]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com", "lambda.amazonaws.com"]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:events:${var.region}:${local.account_id}:rule/${var.project}-*", aws_lambda_function.ingest.arn]
    }
  }
}

resource "aws_sqs_queue_policy" "ingest_dlq" {
  queue_url = aws_sqs_queue.ingest_dlq.id
  policy    = data.aws_iam_policy_document.ingest_dlq.json
}

resource "aws_cloudwatch_metric_alarm" "ingest_dlq" {
  alarm_name          = "${var.project}-ingest-dlq-not-empty"
  alarm_description   = "An upload event failed the doorbell twice and is parked; replay it (drill 07)"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.ingest_dlq.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [local.topic_arn]
  ok_actions          = [local.topic_arn]
}
