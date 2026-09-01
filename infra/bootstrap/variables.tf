variable "region" {
  description = "AWS region for the state bucket and the budget (IAM and OIDC are global)."
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Tag value applied to every resource; also the prefix of every name."
  type        = string
  default     = "steakllm"
}

variable "github_owner" {
  description = "GitHub user or organisation that owns the repository (the part before the slash)."
  type        = string
}

variable "github_repo" {
  description = "Repository name (the part after the slash)."
  type        = string
  default     = "SteakLLM"
}

variable "github_owner_id" {
  description = "Numeric ID of the owner (gh api users/<owner> --jq .id). GitHub's immutable OIDC subject is repo:<owner>@<owner_id>/<repo>@<repo_id>:…"
  type        = number
}

variable "github_repo_id" {
  description = "Numeric ID of the repository (gh api repos/<owner>/<repo> --jq .id). Survives renames; names don't."
  type        = number
}

variable "budget_email" {
  description = "Address that receives the budget alarms. Lives in terraform.tfvars (git-ignored); in CI, in the TF_VAR_BUDGET_EMAIL secret."
  type        = string
  # A missing CI secret arrives as an empty string; fail loudly instead of planning a broken alarm (Incident 8).
  validation {
    condition     = can(regex("^[^@]+@[^@]+$", var.budget_email))
    error_message = "budget_email must be a plausible email address; an empty value usually means the TF_VAR_BUDGET_EMAIL secret is unset."
  }
}

variable "monthly_budget_usd" {
  description = "Monthly cost ceiling; alarms fire at 80% actual, 100% actual and 100% forecast."
  type        = number
  default     = 100
}
