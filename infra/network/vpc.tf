# The neighbourhood: one VPC, two AZs, public and private subnets, one way in (IGW, for the public
# subnets only) and — in nat.tf — one way out for the private ones.

resource "aws_vpc" "this" {
  #checkov:skip=CKV2_AWS_11:Flow logs off on purpose (~$1-5/month for a one-node platform observed at the pod level); a Step 10 drill turns them on
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true # EKS and the endpoints need private DNS names to resolve
  tags                 = { Name = var.project }
}

# The VPC's default security group allows everything between its members by default; nothing here
# uses it, so it is emptied: a resource that slips into "default" gets no rules at all.
resource "aws_default_security_group" "empty" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.project}-default-empty" }
}

# Flow logs are deliberately off: ~$1–5/month of CloudWatch for a single-node platform whose traffic
# is observed at the pod level (Step 8). Turn on for a security drill (Step 10).

# ---- public subnets: load balancer (Step 8) and the NAT instance ---------------------------------

resource "aws_subnet" "public" {
  count                   = length(var.azs)
  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.azs[count.index]
  map_public_ip_on_launch = false # nothing gets a public address by accident; the NAT's EIP is explicit
  tags = {
    Name                                        = "${var.project}-public-${var.azs[count.index]}"
    Tier                                        = "public"
    "kubernetes.io/role/elb"                    = "1" # the AWS load-balancer controller places the ALB here
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
  }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = var.project }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.project}-public" }
}

resource "aws_route" "public_default" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  count          = length(var.azs)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# ---- private subnets: nodes and pods --------------------------------------------------------------

resource "aws_subnet" "private" {
  count                   = length(var.azs)
  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.private_subnet_cidrs[count.index]
  availability_zone       = var.azs[count.index]
  map_public_ip_on_launch = false
  tags = {
    Name                                        = "${var.project}-private-${var.azs[count.index]}"
    Tier                                        = "private"
    "kubernetes.io/role/internal-elb"           = "1" # internal load balancers (tailnet-only services) go here
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    "karpenter.sh/discovery"                    = var.project # Step 9's Karpenter finds its subnets by this tag
  }
}

# One private route table for both AZs: its default route is the NAT instance's ENI (nat.tf).
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "${var.project}-private" }
}

resource "aws_route_table_association" "private" {
  count          = length(var.azs)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# ---- gateway endpoints: free private roads to S3 and DynamoDB -------------------------------------
# A gateway endpoint is a route-table entry, not a network interface: traffic to the service's prefix
# list goes straight to AWS's backbone. No hourly charge, no per-GB charge, and it never touches the NAT.

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id, aws_route_table.public.id]
  tags              = { Name = "${var.project}-s3" }
}

resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${var.region}.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id, aws_route_table.public.id]
  tags              = { Name = "${var.project}-dynamodb" }
}
