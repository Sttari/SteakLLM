# Two security groups, one door (ADR-0012). The Kafka door is the internal NLB the AWS Load Balancer
# Controller builds for Strimzi's `lambda` listener; it admits exactly one thing: the ingest Lambda's group,
# on the listener's port. The Lambda's group may speak to the door, and to S3 and DynamoDB through the VPC's
# gateway endpoints (their prefix lists) — nothing else, so the Lambda needs no NAT and no internet.

resource "aws_security_group" "ingest_lambda" {
  #checkov:skip=CKV2_AWS_5:attached to the ingest Lambda in 10.4 (same module, next substep)
  name        = "${var.project}-ingest-lambda"
  description = "The ingest Lambda ENIs: Kafka door, S3 and DynamoDB endpoints only"
  vpc_id      = data.terraform_remote_state.network.outputs.vpc_id
  tags        = { Name = "${var.project}-ingest-lambda" }
}

resource "aws_security_group" "kafka_door" {
  #checkov:skip=CKV2_AWS_5:attached by the AWS Load Balancer Controller to the NLB it builds from the Strimzi listener's annotation (by name)
  name        = "${var.project}-kafka-door"
  description = "The internal NLB in front of the Strimzi lambda listener: the ingest Lambda only"
  vpc_id      = data.terraform_remote_state.network.outputs.vpc_id
  tags        = { Name = "${var.project}-kafka-door" }
}

resource "aws_vpc_security_group_egress_rule" "lambda_to_door" {
  security_group_id            = aws_security_group.ingest_lambda.id
  description                  = "Kafka through the door"
  ip_protocol                  = "tcp"
  from_port                    = var.kafka_door_port
  to_port                      = var.kafka_door_port
  referenced_security_group_id = aws_security_group.kafka_door.id
}

resource "aws_vpc_security_group_egress_rule" "lambda_to_s3" {
  security_group_id = aws_security_group.ingest_lambda.id
  description       = "S3 over the gateway endpoint"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  prefix_list_id    = data.aws_prefix_list.s3.id
}

resource "aws_vpc_security_group_egress_rule" "lambda_to_dynamodb" {
  security_group_id = aws_security_group.ingest_lambda.id
  description       = "DynamoDB over the gateway endpoint"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  prefix_list_id    = data.aws_prefix_list.dynamodb.id
}

resource "aws_vpc_security_group_ingress_rule" "door_from_lambda" {
  security_group_id            = aws_security_group.kafka_door.id
  description                  = "The ingest Lambda"
  ip_protocol                  = "tcp"
  from_port                    = var.kafka_door_port
  to_port                      = var.kafka_door_port
  referenced_security_group_id = aws_security_group.ingest_lambda.id
}

# The NLB forwards to the broker pods (target type ip); the controller adds the matching rule to the
# cluster security group itself (manage-backend-security-group-rules), so nothing here names the cluster.
resource "aws_vpc_security_group_egress_rule" "door_to_vpc" {
  security_group_id = aws_security_group.kafka_door.id
  description       = "To the broker pods"
  ip_protocol       = "tcp"
  from_port         = var.kafka_door_port
  to_port           = var.kafka_door_port
  cidr_ipv4         = data.terraform_remote_state.network.outputs.vpc_cidr
}
