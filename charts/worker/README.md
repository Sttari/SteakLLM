# charts/worker — one chart, three consumers

The embedder, the summarizer and the notifier are Kafka consumers with no callers: a Deployment, a ServiceAccount named after the service (Pod Identity, `infra/platform`), a ConfigMap of settings, probes on the consumer's own `/healthz` and `/readyz` (8080), the `steakllm.io/role: worker` label the NetworkPolicies select on, the restricted security context, the CPU node. Each `platform/apps/<service>.yaml` sets `name`, `image.tag` and `config`; the summarizer adds `secretEnv` for the gateway key.

`helm template embedder charts/worker --set name=embedder --set image.repository=…/steakllm/embedder --set image.tag=sha-…`
