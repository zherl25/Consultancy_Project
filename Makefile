.DEFAULT_GOAL := help

.PHONY: help dev prod down logs clean run

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

dev: ## Start dev environment with hot reload and bind-mounts
	docker compose -f docker-compose-dev.yaml up --build

prod: ## Build and start production environment (detached)
	docker compose up --build -d

down: ## Stop all running containers
	docker compose down

logs: ## Stream logs from all running containers
	docker compose logs -f

clean: ## Stop containers and remove all volumes (destructive — wipes vector store)
	docker compose down -v --remove-orphans

run: ## Run locally without Docker (requires active venv)
	python run.py
