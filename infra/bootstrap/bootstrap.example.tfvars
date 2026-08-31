# Copy to terraform.tfvars (git-ignored) and fill in. Only these values are yours; everything else has a default.
github_owner    = "your-github-username"
github_owner_id = 0 # gh api users/<owner> --jq .id
github_repo_id  = 0 # gh api repos/<owner>/SteakLLM --jq .id
budget_email    = "you@example.com"
