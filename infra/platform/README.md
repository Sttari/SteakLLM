# infra/platform — what the cluster's tenants need from AWS

Applied by the pipeline **after `eks`** (the Pod Identity associations need the cluster). State key `platform/terraform.tfstate`. Reads no other module's state on purpose: while the cluster is down, `eks`'s state is empty, and a plan on a pull request must still succeed — so the cluster name is a variable, and the association is simply re-created by the next apply after a rebuild.

| What | Where | Why |
|---|---|---|
| Secrets Manager slots `steakllm/gateway`, `steakllm/tailscale`, `steakllm/grafana` | `secrets.tf` | Names in Terraform, values from a human's terminal; External Secrets copies them into the cluster |
| Pod Identity roles `steakllm-external-secrets`, `-gateway`, `-embedder`, `-notifier` with least-privilege inline policies | `pod-identity.tf` | Each service wears its own hat; the bucket, table and topic are named now and created in Step 10 |
| Associations `external-secrets/external-secrets`, `steakllm/gateway`, `steakllm/embedder`, `steakllm/notifier` | `pod-identity.tf` | The binding service account → role; nothing in the chart says "role ARN" |

**Filling the slots** (from a terminal, never through a file in the repo; the values never echo):

```
aws secretsmanager put-secret-value --secret-id steakllm/gateway   --secret-string "{\"api_key\":\"$(openssl rand -hex 24)\",\"demo_key\":\"$(openssl rand -hex 16)\"}"
aws secretsmanager put-secret-value --secret-id steakllm/grafana   --secret-string "{\"admin-user\":\"admin\",\"admin-password\":\"$(openssl rand -base64 24)\"}"
aws secretsmanager put-secret-value --secret-id steakllm/tailscale --secret-string '{"client_id":"<paste>","client_secret":"<paste>"}'
```

Read a value only when you must, and only to your own screen: `aws secretsmanager get-secret-value --secret-id steakllm/gateway --query SecretString --output text`.

**Cost:** three secrets at $0.40/month each; roles and associations are free.
