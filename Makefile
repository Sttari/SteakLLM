.PHONY: help lint test build up down nuke ps logs demo e2e

# One .env at the repo root serves Compose and the services alike (see .env.example).
COMPOSE := docker compose --env-file .env --profile services -f compose/compose.yaml

help: ## list targets
	@grep -E "^[a-z]+:.*## " $(MAKEFILE_LIST) | awk -F ":.*## " '{printf "  %-8s %s\n", $$1, $$2}'

lint: ## run every pre-commit hook on the whole tree
	pre-commit run --all-files

test: ## run every Python package's tests from its lockfile (same loop as ci.yml)
	@for dir in services/*/; do \
	  [ -f "$$dir/pyproject.toml" ] || continue; \
	  echo "== $$dir"; uv sync --directory "$$dir" --frozen -q && uv run --directory "$$dir" pytest || exit 1; \
	done

# Two phases: `--wait` counts a one-shot container that exited 0 as a failure (Incident 16), so the
# long-running services are waited on first, then the init containers run and their exit codes are checked.
INFRA    := minio dynamodb qdrant kafka ollama vllm-stub open-webui
SERVICES := $(INFRA) gateway ingest embedder summarizer notifier
INITS    := minio-init dynamodb-init kafka-init ollama-init

build: ## build the five service images (multi-stage, non-root)
	$(COMPOSE) build gateway ingest embedder summarizer notifier

up: ## start the local dev stack (infra + the five services): wait for healthy, then run the inits
	$(COMPOSE) up -d --wait $(INFRA)
	$(COMPOSE) up -d $(INITS)
	@$(COMPOSE) wait $(INITS) >/dev/null
	$(COMPOSE) up -d --wait gateway ingest embedder summarizer notifier
	@$(COMPOSE) ps -a --format 'table {{.Service}}\t{{.Status}}'

down: ## stop the local dev stack (data volumes are kept; see nuke)
	$(COMPOSE) down

nuke: ## stop the stack AND delete its volumes: documents, catalog, vectors, Kafka log, model weights (human-only)
	@echo "This deletes every local volume: MinIO documents, DynamoDB catalog, Qdrant vectors, Kafka log, Ollama weights."
	@read -p "Type 'nuke' to confirm: " a && [ "$$a" = "nuke" ] || { echo "aborted"; exit 1; }
	$(COMPOSE) down -v

ps: ## show the stack's services and health
	@$(COMPOSE) ps -a --format 'table {{.Service}}\t{{.Status}}'

logs: ## follow the stack's logs (SERVICE=name for one service)
	$(COMPOSE) logs -f $(SERVICE)

e2e: ## the end-to-end test against the running stack: upload → summarized → docs answer, under 60 s
	uv run --with pytest --with httpx tests/e2e/test_pipeline.py

demo: ## drive the sample PDF through the stack by hand: MinIO → Kafka → Ollama → Qdrant → Bedrock → catalog
	uv run compose/demo.py

# ---- the cluster, dev-time posture (Step 8.11): on while we work, off when we stop ------------------
# cluster-up: rebuild through the pipeline (four gates), point kubectl at it, bootstrap Argo once.
# cluster-down: remove anything a controller made outside Kubernetes (load balancers), then tear eks down.
# Both approve the production gates from the laptop with gh — the human is the one typing make.
ENV_ID := 21032992457

cluster-up: ## rebuild the cluster (apply.yml, five gates) and bootstrap Argo CD through an SSM tunnel; ~25 min
	@gh workflow run apply.yml && sleep 30 && RUN=$$(gh run list --workflow apply --branch main --limit 1 --json databaseId --jq '.[0].databaseId') && echo "apply run $$RUN" && \
	for gate in ecr network eks platform gpu; do until [ "$$(gh api repos/Sttari/SteakLLM/actions/runs/$$RUN/pending_deployments --jq length)" = 1 ] || [ "$$(gh run view $$RUN --json status --jq .status)" = completed ]; do sleep 15; done; \
	  gh api -X POST repos/Sttari/SteakLLM/actions/runs/$$RUN/pending_deployments -F 'environment_ids[]=$(ENV_ID)' -f state=approved -f comment="cluster-up: $$gate" >/dev/null 2>&1 && echo "$$gate approved"; sleep 45; done && \
	until [ "$$(gh run view $$RUN --json status --jq .status)" = completed ]; do sleep 20; done && gh run view $$RUN --json conclusion --jq '"apply: " + .conclusion'
	aws eks update-kubeconfig --name steakllm --region us-east-1
	$(MAKE) bootstrap-argo

# The API is private-only (8.9) and the tailnet router that reaches it runs inside the cluster — which a
# fresh cluster does not have yet (Incident 34). So the bootstrap goes through a Session Manager tunnel
# via the NAT instance (in the VPC, SSM-managed): local 6443 → the API's private address, with the TLS
# name pinned to the endpoint's hostname. Needs the Session Manager plugin on the laptop.
bootstrap-argo: ## the one hand step, through an SSM tunnel: helm install argocd + the root Application
	$(eval NAT := $(shell aws ec2 describe-instances --filters Name=tag:Name,Values=steakllm-nat Name=instance-state-name,Values=running --query 'Reservations[0].Instances[0].InstanceId' --output text))
	$(eval API := $(shell aws eks describe-cluster --name steakllm --query cluster.endpoint --output text | sed 's#https://##'))
	@echo "tunnel: localhost:6443 → $(API):443 via $(NAT)"
	@aws ssm start-session --target $(NAT) --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters 'host=$(API),portNumber=443,localPortNumber=6443' >/tmp/steakllm-ssm-tunnel.log 2>&1 & echo $$! > /tmp/steakllm-ssm-tunnel.pid; sleep 6
	@kubectl config set-cluster arn:aws:eks:us-east-1:066591056087:cluster/steakllm --server=https://localhost:6443 --tls-server-name=$(API) >/dev/null
	kubectl get --raw /healthz
	helm repo add argo https://argoproj.github.io/argo-helm >/dev/null 2>&1 || true
	helm install argocd argo/argo-cd --version 10.7.0 --namespace argocd --create-namespace -f platform/argocd/values.yaml --wait --timeout 10m
	kubectl apply -f platform/root.yaml
	@echo "waiting for the Tailscale router to come up (then the tunnel can go)…"; n=0; until kubectl get connector steakllm-vpc -o jsonpath='{.status.conditions[?(@.type=="ConnectorReady")].status}' 2>/dev/null | grep -q True || [ $$n -ge 60 ]; do sleep 15; n=$$((n+1)); done
	@kill $$(cat /tmp/steakllm-ssm-tunnel.pid) 2>/dev/null; rm -f /tmp/steakllm-ssm-tunnel.pid
	aws eks update-kubeconfig --name steakllm --region us-east-1
	@echo "Argo is bootstrapped; the tailnet carries kubectl from here: kubectl -n argocd get applications -w"

cluster-down: ## take the workloads down through Argo, remove their volumes, then tear eks down (teardown.yml, one gate); the network stays
	@echo "1/4 Removing Ingresses and LoadBalancer Services (an ALB outlives the cluster and keeps billing)…"
	-kubectl get ingress -A --no-headers 2>/dev/null | awk '{print "-n "$$1" "$$2}' | xargs -r -L1 kubectl delete ingress
	-kubectl get svc -A --field-selector spec.type=LoadBalancer --no-headers 2>/dev/null | awk '{print "-n "$$1" "$$2}' | xargs -r -L1 kubectl delete svc
	@until [ "$$(aws elbv2 describe-load-balancers --query 'length(LoadBalancers)' --output text)" = 0 ]; do echo "waiting for load balancers to go…"; sleep 15; done
	@echo "2/4 Taking the workloads down through Argo (cascade), so their claims can be released…"
	@# Every workload Application gets the cascade finalizer, then is removed. Kept alive: argocd (must outlive its
	@# children), root (removed last, without cascade), namespaces (would take everything with them), storage,
	@# network-policies, and tailscale + tailscale-config — the subnet router is the laptop's ONLY path to the
	@# private API; taking it down mid-run cut this very target off from the cluster (Incident 33b).
	-for a in $$(kubectl -n argocd get applications -o jsonpath='{.items[*].metadata.name}'); do case $$a in argocd|root|namespaces|storage|network-policies|tailscale|tailscale-config) ;; *) \
	  kubectl -n argocd patch application $$a --type merge -p '{"metadata":{"finalizers":["resources-finalizer.argocd.argoproj.io"]}}' >/dev/null && kubectl -n argocd delete application $$a --wait=false;; esac; done
	-kubectl -n argocd patch application root --type merge -p '{"metadata":{"finalizers":null}}' >/dev/null
	-kubectl -n argocd delete application root --wait=false
	@n=0; until [ "$$(kubectl get pods -A --request-timeout=10s --no-headers 2>/dev/null | grep -vE '^(kube-system|argocd|tailscale|external-secrets) ' | wc -l | tr -d ' ')" = 0 ] || [ $$n -ge 40 ]; do echo "waiting for workload pods to go…"; sleep 15; n=$$((n+1)); done
	@echo "3/4 Deleting every PersistentVolumeClaim so the EBS driver removes the volumes (a torn-down cluster cannot)…"
	-kubectl delete pvc --all --all-namespaces --wait=true --timeout=5m
	@n=0; until [ "$$(aws ec2 describe-volumes --filters Name=tag-key,Values=kubernetes.io/created-for/pvc/name --query 'length(Volumes)' --output text)" = 0 ] || [ $$n -ge 20 ]; do echo "waiting for PVC volumes to go…"; sleep 15; n=$$((n+1)); done
	@echo "4/4 Tearing eks down through the pipeline…"
	gh workflow run teardown.yml -f module=eks -f confirm=eks && sleep 30 && RUN=$$(gh run list --workflow teardown --limit 1 --json databaseId --jq '.[0].databaseId') && \
	until [ "$$(gh api repos/Sttari/SteakLLM/actions/runs/$$RUN/pending_deployments --jq length)" = 1 ]; do sleep 15; done && \
	gh api -X POST repos/Sttari/SteakLLM/actions/runs/$$RUN/pending_deployments -F 'environment_ids[]=$(ENV_ID)' -f state=approved -f comment="cluster-down" >/dev/null && echo "teardown approved" && \
	until [ "$$(gh run view $$RUN --json status --jq .status)" = completed ]; do sleep 20; done && gh run view $$RUN --json conclusion --jq '"teardown: " + .conclusion'
	@echo "meter check:" && aws eks describe-cluster --name steakllm --query cluster.status --output text 2>&1 | grep -oE 'ResourceNotFoundException|ACTIVE|DELETING' && echo "load balancers: $$(aws elbv2 describe-load-balancers --query 'length(LoadBalancers)' --output text) · volumes: $$(aws ec2 describe-volumes --query 'length(Volumes)' --output text) · orphaned (available): $$(aws ec2 describe-volumes --filters Name=status,Values=available --query 'length(Volumes)' --output text)"
