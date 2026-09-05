output "ingest_lambda_security_group_id" {
  value = aws_security_group.ingest_lambda.id
}

output "kafka_door_security_group_id" {
  description = "Named steakllm-kafka-door; the Strimzi listener's annotation refers to it by name."
  value       = aws_security_group.kafka_door.id
}
