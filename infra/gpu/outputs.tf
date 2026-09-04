output "models_bucket" {
  description = "Where the weights live; the mirror Job writes s3://<bucket>/<model prefix>/, vLLM reads it."
  value       = aws_s3_bucket.models.bucket
}

output "vllm_repository_url" {
  description = "The mirrored vLLM image: <url>:<vllm version>."
  value       = aws_ecr_repository.vllm.repository_url
}

output "karpenter_queue_name" {
  description = "settings.interruptionQueue for the Karpenter chart."
  value       = aws_sqs_queue.karpenter.name
}

output "karpenter_role_arn" {
  value = aws_iam_role.karpenter.arn
}

output "reaper_function_name" {
  description = "aws lambda invoke --function-name <this> /dev/stdout — the 9.7 drill."
  value       = aws_lambda_function.reaper.function_name
}
