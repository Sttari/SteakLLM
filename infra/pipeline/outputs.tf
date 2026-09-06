output "ingest_lambda_security_group_id" {
  value = aws_security_group.ingest_lambda.id
}

output "kafka_door_security_group_id" {
  description = "Named steakllm-kafka-door; the Strimzi listener's annotation refers to it by name."
  value       = aws_security_group.kafka_door.id
}

output "ingest_function_name" {
  value = aws_lambda_function.ingest.function_name
}

output "ingest_dlq_url" {
  value = aws_sqs_queue.ingest_dlq.id
}

output "kafka_bootstrap_through_the_door" {
  value = local.kafka_bootstrap
}
