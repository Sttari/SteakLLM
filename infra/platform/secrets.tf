# Three slots in Secrets Manager. Terraform creates the *name*; a human puts the *value* in from a
# terminal (`aws secretsmanager put-secret-value`), so no secret is ever in git, in a plan, or in a
# chat. External Secrets (8.3) copies them into the cluster wearing the external-secrets role below.
# $0.40/month each.

locals {
  secrets = {
    gateway   = "The gateway's API keys: {\"api_key\": …, \"demo_key\": …}"
    tailscale = "The Tailscale operator's OAuth client: {\"client_id\": …, \"client_secret\": …}"
    grafana   = "Grafana's admin login: {\"admin-user\": \"admin\", \"admin-password\": …}"
    argocd    = "Argo CD's admin password (plain; External Secrets writes the bcrypt hash into argocd-secret): {\"password\": …}"
  }
}

resource "aws_secretsmanager_secret" "this" {
  #checkov:skip=CKV2_AWS_57:No automatic rotation: these are keys we mint ourselves, rotated by hand with a new put-secret-value; ESO picks the new value up within its refresh interval
  #checkov:skip=CKV_AWS_149:AWS-managed encryption key; a customer key adds $1/month per key for the same at-rest guarantee
  for_each                = local.secrets
  name                    = "${var.project}/${each.key}"
  description             = each.value
  recovery_window_in_days = var.secret_recovery_days
}

# The value is never set here. `secret_string` lives outside Terraform; a plan will never show it.
