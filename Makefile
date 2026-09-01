.PHONY: help lint test up down demo

help: ## list targets
	@grep -E "^[a-z]+:.*## " $(MAKEFILE_LIST) | awk -F ":.*## " '{printf "  %-8s %s\n", $$1, $$2}'

lint: ## run every pre-commit hook on the whole tree
	pre-commit run --all-files

test: ## run the test suites (Step 4+)
	@echo "not yet"

up: ## start the local dev stack (Step 5)
	@echo "not yet"

down: ## stop the local dev stack (Step 5)
	@echo "not yet"

demo: ## drop a sample document into the local stack (Step 5)
	@echo "not yet"
