# The one door out (ADR-0007): a t4g.nano running fck-nat.
#
# The private route table points at a *static* network interface (ENI) that carries the Elastic IP,
# and that ENI is the instance's primary interface. Nothing is attached at boot, so nothing can fail
# to attach (Incident 26: the first design — a disposable instance in an autoscaling group attaching
# the ENI on boot — could not reach the EC2 API to do the attaching, because its only public address
# was on the ENI it had not attached yet). Hardware failure: EC2's simplified automatic recovery
# restarts the instance on new hardware with the same ENI. Anything else: Terraform re-creates it —
# a few minutes without egress, and the route never changes.

data "aws_ami" "fck_nat" {
  most_recent = true
  owners      = ["568608671756"] # fck-nat's publishing account
  filter {
    name   = "name"
    values = ["fck-nat-al2023-*-arm64-ebs"]
  }
  filter {
    name   = "architecture"
    values = ["arm64"]
  }
}

resource "aws_security_group" "nat" {
  name        = "${var.project}-nat"
  description = "NAT instance: accepts traffic from inside the VPC only; answers to the internet"
  vpc_id      = aws_vpc.this.id
  tags        = { Name = "${var.project}-nat" }
}

resource "aws_vpc_security_group_ingress_rule" "nat_from_vpc" {
  security_group_id = aws_security_group.nat.id
  description       = "Everything from inside the VPC (the private subnets route through here)"
  cidr_ipv4         = aws_vpc.this.cidr_block
  ip_protocol       = "-1"
}

resource "aws_vpc_security_group_egress_rule" "nat_to_anywhere" {
  security_group_id = aws_security_group.nat.id
  description       = "Forwarded traffic to the internet"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

# The static ENI in the first public subnet. source_dest_check off: a NAT forwards packets that are
# not addressed to itself, which the check would otherwise drop.
resource "aws_network_interface" "nat" {
  subnet_id         = aws_subnet.public[0].id
  security_groups   = [aws_security_group.nat.id]
  source_dest_check = false
  tags              = { Name = "${var.project}-nat" }
}

resource "aws_eip" "nat" {
  #checkov:skip=CKV2_AWS_19:The EIP is attached to the static ENI (aws_eip_association), which is the instance's primary interface; checkov only recognises instance attachments
  domain = "vpc"
  tags   = { Name = "${var.project}-nat" }
}

resource "aws_eip_association" "nat" {
  allocation_id        = aws_eip.nat.id
  network_interface_id = aws_network_interface.nat.id
}

# The private subnets' way out.
resource "aws_route" "private_default" {
  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  network_interface_id   = aws_network_interface.nat.id
}

# ---- the instance -------------------------------------------------------------------------------

# Session Manager (SSM) is the only way in: no SSH port, no key pair, an audited shell from the AWS
# console or `aws ssm start-session`. Incident 26 was diagnosed blind because this was missing.
data "aws_iam_policy_document" "nat_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "nat" {
  name               = "${var.project}-nat-instance"
  assume_role_policy = data.aws_iam_policy_document.nat_assume.json
}

resource "aws_iam_role_policy_attachment" "nat_ssm" {
  role       = aws_iam_role.nat.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "nat" {
  name = "${var.project}-nat-instance"
  role = aws_iam_role.nat.name
}

resource "aws_instance" "nat" {
  #checkov:skip=CKV_AWS_126:Detailed (1-minute) monitoring costs $2.10/month per instance; 5-minute metrics are enough for a NAT
  ami                  = data.aws_ami.fck_nat.id
  instance_type        = var.nat_instance_type
  ebs_optimized        = true
  iam_instance_profile = aws_iam_instance_profile.nat.name

  # The static ENI *is* the primary interface: the EIP, the route and the security group all live on it.
  network_interface {
    network_interface_id = aws_network_interface.nat.id
    device_index         = 0
  }

  metadata_options {
    http_tokens                 = "required" # IMDSv2 only
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_size = 8
    volume_type = "gp3"
    encrypted   = true
  }

  # fck-nat needs no configuration when it NATs through its primary interface; /etc/fck-nat.conf stays empty.
  tags = { Name = "${var.project}-nat" }

  lifecycle {
    # A new fck-nat AMI must not replace the door as a side effect of an unrelated apply.
    # To patch: `terraform apply -replace=aws_instance.nat` through the pipeline, on purpose.
    ignore_changes = [ami]
  }
}
