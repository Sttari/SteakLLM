# infra/gpu — the AWS side of the GPU pool

Applied by the pipeline after `platform` (the Pod Identity associations need the cluster). State key `gpu/terraform.tfstate`. Survives cluster teardowns on purpose: the bucket and the mirrored image are what make a cold start fast.

| What | Where | Why |
|---|---|---|
| Models bucket `steakllm-models-<account>` (private, versioned, AES256, tidy lifecycle) | `bucket.tf` | The weights, in our account, read over the free S3 endpoint (ADR-0011) |
| ECR `steakllm/vllm` (immutable, scan on push, keep 3) | `ecr.tf` | The vLLM image, in-region, pulled by the GPU node |
| Karpenter controller role (Pod Identity `karpenter/karpenter`), scoped by cluster and nodepool tags; the interruption queue and its four EventBridge rules | `karpenter.tf` | Launch and remove tagged machines, nothing else; two minutes' warning before AWS takes one |
| Pod Identity roles `steakllm/mirror` (write weights, push the image) and `steakllm/vllm` (read weights) | `roles.tf` | The mirror Jobs (9.3) and vLLM (9.5) wear their own hats |
| The nightly reaper: Lambda + 03:00 UTC schedule; may terminate only instances tagged `karpenter.sh/nodepool = gpu` | `reaper.tf`, `lambda/reaper.py` | The line behind Karpenter's line |

The cluster's security group carries the `karpenter.sh/discovery` tag from `infra/eks` (the module that owns the cluster); the private subnets already carry it from `infra/network`.

**Cost standing:** bucket ≈ $0.35/month, image ≈ $1/month, queue/rules/Lambda cents. The GPU itself bills only while a NodePool has a machine.

**Drill (9.7):** `aws lambda invoke --function-name $(terraform output -raw reaper_function_name) /dev/stdout` with a GPU node present.
