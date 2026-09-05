# Strimzi's cluster CA, so the Lambda can verify the broker behind the door. The slot is created empty;
# a named hand step fills it from the cluster (kubectl get secret … | aws secretsmanager put-secret-value),
# never through a terminal that prints it. A CA renewal (Strimzi rotates yearly) is a re-fill.
resource "aws_secretsmanager_secret" "kafka_ca" {
  #checkov:skip=CKV2_AWS_57:No automatic rotation: Strimzi renews its CA on its own schedule; the slot is re-filled by hand then
  #checkov:skip=CKV_AWS_149:AWS-managed encryption key for a public certificate
  name                    = "${var.project}/kafka-ca"
  description             = "Strimzi cluster CA (PEM) for clients outside the cluster: the ingest Lambda"
  recovery_window_in_days = 0
}
