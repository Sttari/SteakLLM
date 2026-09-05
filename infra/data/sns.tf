# Notifications: the notifier publishes SummaryReady matches here; Thomas's inbox is the first subscriber
# (confirmed by the click in the email SNS sends). 10.4's dead-letter alarm publishes here too.
resource "aws_sns_topic" "notifications" {
  #checkov:skip=CKV_AWS_26:Email delivery from a KMS-encrypted topic needs a key policy for SNS and $1/month; the payload is a document title and a summary line
  name = "${var.project}-notifications"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.notifications.arn
  protocol  = "email"
  endpoint  = var.notify_email
}
