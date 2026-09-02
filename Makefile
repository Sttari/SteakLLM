.PHONY: help lint test up down nuke ps logs demo

# One .env at the repo root serves Compose and the services alike (see .env.example).
COMPOSE := docker compose --env-file .env -f compose/compose.yaml

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
SERVICES := minio dynamodb qdrant kafka ollama vllm-stub open-webui
INITS    := minio-init dynamodb-init kafka-init ollama-init

up: ## start the local dev stack: wait for every service to be healthy, then run the one-shot inits
	$(COMPOSE) up -d --wait $(SERVICES)
	$(COMPOSE) up -d $(INITS)
	@$(COMPOSE) wait $(INITS) >/dev/null
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

demo: ## drive the sample PDF through the stack by hand: MinIO → Kafka → Ollama → Qdrant → Bedrock → catalog
	uv run compose/demo.py
