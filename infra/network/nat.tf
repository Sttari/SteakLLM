# The one door out (ADR-0007): a t4g.nano running fck-nat, replaced automatically when it dies.
#
# How replacement works without touching the routes: the private route table points at a *static*
# network interface (ENI) that we create here and that carries the Elastic IP. The instance itself is
# disposable — an autoscaling group of one launches it from a template, and on boot fck-nat attaches
# that ENI to itself (its config file names the ENI). A dead instance is replaced in a couple of
# minutes; the ENI, the EIP and the route never change.

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
  #checkov:skip=CKV2_AWS_19:The EIP is attached to the static ENI (aws_eip_association), which the disposable instance attaches on boot; checkov only recognises instance attachments
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

# ---- the disposable instance ----------------------------------------------------------------------

# The instance may attach *its* ENI and nothing else (fck-nat's boot script does the attaching).
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

data "aws_iam_policy_document" "nat_attach_eni" {
  # AttachNetworkInterface is authorised against both the ENI and the instance: our one ENI, and any
  # instance tagged as this project's NAT (the tag propagates from the autoscaling group at launch).
  statement {
    sid     = "AttachOurEniToOurInstance"
    actions = ["ec2:AttachNetworkInterface"]
    resources = [
      aws_network_interface.nat.arn,
      "arn:aws:ec2:${var.region}:${data.aws_caller_identity.current.account_id}:instance/*",
    ]
    condition {
      test     = "StringEqualsIfExists"
      variable = "aws:ResourceTag/Name"
      values   = ["${var.project}-nat"]
    }
  }
  statement {
    sid       = "TuneOurEni"
    actions   = ["ec2:ModifyNetworkInterfaceAttribute"]
    resources = [aws_network_interface.nat.arn]
  }
  statement {
    sid       = "FindOurEni"
    actions   = ["ec2:DescribeNetworkInterfaces"] # read-only; Describe* accepts no resource ARN
    resources = ["*"]
  }
}

data "aws_caller_identity" "current" {}

resource "aws_iam_role_policy" "nat" {
  name   = "attach-the-nat-eni"
  role   = aws_iam_role.nat.id
  policy = data.aws_iam_policy_document.nat_attach_eni.json
}

resource "aws_iam_instance_profile" "nat" {
  name = "${var.project}-nat-instance"
  role = aws_iam_role.nat.name
}

resource "aws_launch_template" "nat" {
  name_prefix   = "${var.project}-nat-"
  image_id      = data.aws_ami.fck_nat.id
  instance_type = var.nat_instance_type
  iam_instance_profile {
    name = aws_iam_instance_profile.nat.name
  }
  network_interfaces {
    associate_public_ip_address = false # the public address is the EIP on the static ENI, not this one
    security_groups             = [aws_security_group.nat.id]
    delete_on_termination       = true
  }
  metadata_options {
    http_tokens                 = "required" # IMDSv2 only
    http_put_response_hop_limit = 1
  }
  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size = 8
      volume_type = "gp3"
      encrypted   = true
    }
  }
  # fck-nat reads /etc/fck-nat.conf on boot: with eni_id set it attaches that ENI and routes through it.
  user_data = base64encode(<<-EOT
    #!/bin/bash
    echo "eni_id=${aws_network_interface.nat.id}" >> /etc/fck-nat.conf
    systemctl restart fck-nat.service
  EOT
  )
  tag_specifications {
    resource_type = "instance"
    tags          = { Name = "${var.project}-nat" }
  }
  update_default_version = true
}

resource "aws_autoscaling_group" "nat" {
  name                = "${var.project}-nat"
  min_size            = 1
  max_size            = 1
  desired_capacity    = 1
  vpc_zone_identifier = [aws_subnet.public[0].id] # same subnet as the ENI: an ENI cannot cross subnets
  launch_template {
    id      = aws_launch_template.nat.id
    version = "$Latest"
  }
  tag {
    key                 = "Name"
    value               = "${var.project}-nat"
    propagate_at_launch = true
  }
  tag {
    key                 = "Project"
    value               = var.project
    propagate_at_launch = true
  }
  depends_on = [aws_eip_association.nat] # the ENI must carry its EIP before the first instance grabs it
}
