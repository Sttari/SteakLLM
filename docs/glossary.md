# Glossary

Every abbreviation and term of art used in this repo, one line each, grouped by where it lives. Analogies in *italics* are the ones we use when explaining the system out loud.

## AWS (Amazon Web Services)

| Term | Stands for | What it is here |
|---|---|---|
| ALB | Application Load Balancer | The one public door: holds the public address, terminates TLS, health-checks the gateway pods and spreads requests across them. Understands HTTP (paths, headers). *The ticket desk.* |
| NLB | Network Load Balancer | ALB's sibling that only sees TCP connections; what you'd put in front of Kafka, not a web API. |
| EC2 | Elastic Compute Cloud | Virtual machines. Every cluster node is one; the GPU node is a `g6.xlarge`, the CPU node a `t4g.large` (the "g" is Graviton, AWS's ARM chip). |
| EKS | Elastic Kubernetes Service | The managed Kubernetes control plane. *The hotel manager.* ~$0.10/hr whether or not anything runs. |
| ECR | Elastic Container Registry | Where built container images are stored, tagged with the git commit. |
| S3 | Simple Storage Service | Object storage: uploaded documents, the model-weights mirror, Terraform state. |
| EBS | Elastic Block Store | A disk attached to a machine; `gp3` is the general-purpose SSD type. |
| SNS | Simple Notification Service | Fan-out messaging to email or Slack; the notifier publishes alerts here. |
| SQS | Simple Queue Service | A plain queue: one reader per message, no replay. The alternative Kafka replaces; also the dead-letter queue for the ingest Lambda. |
| IAM | Identity and Access Management | Who may do what. A *role* is a hat anyone trusted may wear for a while. |
| ACM | AWS Certificate Manager | Free TLS certificates for the ALB. |
| WAF | Web Application Firewall | Rate limits, body-size limits and bot filtering in front of the ALB. |
| MSK | Managed Streaming for Apache Kafka | AWS's hosted Kafka; the right answer at work, ~$70+/mo here, so we run Strimzi instead. |
| AMI | Amazon Machine Image | The disk template a node boots from. |
| ARN | Amazon Resource Name | The unique ID string of any AWS resource. |
| PITR | Point-in-Time Recovery | DynamoDB's continuous backup. |
| Lambda | — | A function that runs only when an event happens; no GPU, 15-minute limit. *The handyman you call when a pipe bursts.* |
| EventBridge | — | Routes events (S3 "object created") to targets with filters; also runs schedules. |
| DynamoDB | — | Serverless key-value table; our document catalog and status. |
| Bedrock | — | AWS's pay-per-token LLM API; the warm-up bridge and fallback for chat. |
| Secrets Manager | — | Where secrets live; nothing secret is ever in git or on disk. |

## Networking and security

| Term | Stands for | What it is here |
|---|---|---|
| VPC | Virtual Private Cloud | Our private slice of AWS's network, cut into subnets. |
| AZ | Availability Zone | One data center inside a region; we use two. |
| NAT | Network Address Translation | How machines in private subnets reach the internet without being reachable from it. A NAT *instance* is ~$4/mo, a NAT *gateway* ~$32/mo. |
| IGW | Internet Gateway | The route from public subnets to the internet. |
| TLS | Transport Layer Security | The encryption behind the "S" in HTTPS. |
| OIDC | OpenID Connect | How GitHub Actions proves "I run from Thomas's repo, main branch" so AWS lends it a role for minutes. *A badge, not a key.* |
| Pod Identity | — | The same trick inside the cluster: one IAM role per pod, least privilege. |
| NetworkPolicy | — | Kubernetes firewall rules between pods; ours are default-deny. |
| Presigned URL | — | A time-limited S3 link that allows exactly one action on one object; how uploads happen without touching the cluster. |
| Tailscale / tailnet | — | The private mesh network; the admin door for Grafana, Argo, Qdrant and Kafka. |
| SIGTERM | Signal: terminate | The "please stop" signal Kubernetes sends a pod; workers must finish and commit offsets before exiting. |
| CVE | Common Vulnerabilities and Exposures | Known vulnerabilities; Trivy scans images for them in CI. |

## Kubernetes and delivery

| Term | Stands for | What it is here |
|---|---|---|
| CI | Continuous Integration | Every push is linted, tested, built and scanned by a robot before a human merges. *The strict editor.* |
| CD | Continuous Delivery | Whenever the approved draft changes, something makes reality match it. Two hands: Terraform for AWS, Argo CD for the cluster. *The librarian.* |
| GitOps | — | The repo is the truth; Argo CD pulls from it and makes the cluster match. Merge = deploy, revert = rollback. |
| IaC | Infrastructure as Code | Terraform's category: the cloud described in text, applied by a tool. |
| Pod | — | One running container (occasionally a couple glued together). |
| Deployment | — | The note "keep N copies of this pod running". |
| Service | — | A stable name and address for a set of pods that come and go. |
| Node | — | A machine in the cluster. |
| Control plane | — | The manager that decides where pods run; what EKS charges for. |
| Helm / chart | — | Manifests with the blanks left as variables plus a values file; `helm upgrade` / `rollback`. |
| Argo CD | — | The in-cluster program that keeps the cluster equal to git. |
| Karpenter | — | Watches for pods nobody can place and launches exactly the right machine; removes it when empty. *The valet.* |
| HPA | Horizontal Pod Autoscaler | Kubernetes' built-in "add replicas when CPU is high". |
| KEDA | Kubernetes Event-Driven Autoscaling | Scales replicas on Kafka lag or a custom metric instead of CPU; what summons the GPU. |
| ESO | External Secrets Operator | Copies secrets from Secrets Manager into the cluster. |
| CNI | Container Network Interface | The plugin that gives each pod its own VPC address. |
| CRD | Custom Resource Definition | How operators like Strimzi and KEDA add new kinds of objects (`Kafka`, `ScaledObject`) to Kubernetes. |
| PVC | Persistent Volume Claim | A pod's request for a disk that outlives it (Kafka's log, Qdrant's data). |
| Taint / toleration | — | A node saying "only pods that explicitly tolerate me may land here"; how the GPU node stays reserved for vLLM. |
| Probe | — | Liveness (restart me if I hang) and readiness (don't send traffic until I'm ready) checks. |
| ADR | Architecture Decision Record | One page per "why", with the alternative we rejected. |
| SLO / SLI | Service Level Objective / Indicator | The promise ("95% of uploads searchable within 90 s") and the measurement behind it. |
| PR | Pull request | The only way `main` changes. |
| SHA | Secure Hash Algorithm | A "git SHA" is a commit's hash; images are tagged with it, never `latest`. |
| DLQ | Dead-Letter Queue | Where a message goes after it has failed too many times, so it can't block the others. |
| OTel | OpenTelemetry | The standard for traces (and metrics and logs); one trace spans upload → Kafka → embed → Qdrant. |
| Loki | — | Log storage searchable across pods, drawn in Grafana. |
| Prometheus / Grafana / Alertmanager | — | The notebook of numbers / the wall of charts / the pager. |
| Trivy / gitleaks / checkov / tflint / kube-linter / ruff | — | Scanners in CI: images, secrets, Terraform security, Terraform style, manifests, Python. |
| Renovate / Dependabot | — | Robots that open PRs to bump pinned versions. |

## Data and messaging

| Term | Stands for | What it is here |
|---|---|---|
| Kafka | — | A durable, ordered log that many independent readers consume at their own pace and can replay. *The notebook in the hallway.* |
| Topic / partition / offset | — | One logbook / a slice of it (ordering is per partition) / a reader's bookmark. |
| Producer / consumer / consumer group | — | Writer / reader / a team of readers that split one topic's partitions among themselves. |
| Consumer lag | — | How far a reader's bookmark trails the last page; the best health signal for the pipeline. |
| Strimzi | — | The Kubernetes operator that runs Kafka for us. |
| KRaft | Kafka Raft | Kafka's built-in consensus; no ZooKeeper. |
| At-least-once | — | S3 and Kafka may deliver the same message twice; consumers must be idempotent. |
| Idempotent | — | Doing it twice has the same result as once; document ID = sha256 of the bytes, Qdrant point ID = hash(doc, chunk). |
| Eventually consistent | — | A document is uploaded before it is searchable; the catalog shows `uploaded → indexed → summarized`. |
| Event-driven | — | A service announces a fact in the past tense (`DocumentUploaded`) and walks away; whoever cares reacts. |
| Qdrant | — | The vector database (embeddings and search). |
| Embedding | — | A list of numbers representing meaning; close vectors = similar text. |
| MinIO | — | S3-compatible storage for the local dev stack. |
| Circuit breaker | — | After repeated failures, stop calling the sick backend for a while, then probe again. |

## LLM (large language model) terms

| Term | Stands for | What it is here |
|---|---|---|
| vLLM | virtual LLM | The inference engine; named after virtual memory because PagedAttention manages the KV cache the way an OS manages RAM. |
| KV cache | Key/Value cache | The attention keys and values of every token in flight; the scarce GPU resource. |
| PagedAttention | — | vLLM's trick of storing the KV cache in small pages, so many requests fit. |
| Continuous batching | — | The batch is re-formed every step; requests join and leave mid-flight. |
| TTFT / TPOT | Time To First Token / Time Per Output Token | Prompt-reading latency / typing speed. |
| FP8 / FP16 | 8-bit / 16-bit floating point | Weight precision; FP8 halves memory and roughly doubles decode speed. |
| Quantization | — | Storing weights in fewer bits; buys latency. Batching buys throughput. |
| RAG | Retrieval-Augmented Generation | Search the documents first, then answer with the found chunks in the prompt. |
| Chunk | — | A slice of a document small enough to embed; heading-aware chunking keeps context. |
| TEI | Text Embeddings Inference | Hugging Face's small embedding server (runs on CPU here). |
| DCGM | Data Center GPU Manager | NVIDIA's exporter for GPU utilization, VRAM and power. |
| VRAM | Video RAM | The GPU's memory (24 GB on the L4). |
| OpenAI contract | — | The `/v1/chat/completions` request/response shape every client and backend speaks; stateless, so the whole conversation travels with each request. |
| Bearer key | — | The API key sent in the `Authorization: Bearer …` header. |
| Tokens per GPU-hour | — | The north-star efficiency metric of self-hosting. |

## Everyday

| Term | Stands for |
|---|---|
| API | Application Programming Interface |
| CLI | Command-Line Interface |
| UI | User Interface |
| HTTP / HTTPS | HyperText Transfer Protocol (Secure) |
| JSON / YAML | JavaScript Object Notation / YAML Ain't Markup Language |
| SSH | Secure Shell |
| PEM | Privacy-Enhanced Mail, the key-file format |
| IP / DNS | Internet Protocol (address) / Domain Name System (Route 53) |
| GPU / CPU | Graphics / Central Processing Unit |
| RAM / IOPS | Random-Access Memory / Input-Output Operations Per Second |
| p95 | The 95th percentile: 95% of requests were at least this fast |
| OSS | Open-Source Software |
| MIT | The license (Massachusetts Institute of Technology) |
