# Equity Research Agent — every command you need, in one place.
#
# First run:
#   make install     backend venv + frontend packages
#   make up          postgres + redis + api + worker + web, in docker
#   make doctor      does this configuration actually work?
#
# Day to day, running the apps natively against dockerised datastores:
#   make up-backend  (or: docker compose up -d db redis)
#   make migrate && make dev-backend   /   make dev-worker   /   make dev-frontend
#
# Every target runs from the repository root. Extra flags go through ARGS:
#   make doctor ARGS="--offline --json"
#   make test ARGS="-k scoring -x"

BACKEND  := backend
FRONTEND := frontend
# Relative to $(BACKEND): every backend recipe cd's there first, because both
# pydantic-settings (env_file=".env") and alembic resolve paths from the working
# directory, not from the repository root.
PY       := .venv/bin/python
COMPOSE  ?= docker compose
ARGS     ?=

.DEFAULT_GOAL := help

.PHONY: help install dev-backend dev-worker dev-frontend migrate doctor test lint \
        seed up down logs up-backend up-frontend clean

help: ## List the available targets
	@echo "Equity Research Agent — make <target>"
	@echo
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo '  Pass flags through with ARGS, e.g. make doctor ARGS="--offline"'

install: ## Create the backend venv (uv) and install frontend packages (npm ci)
	@command -v uv >/dev/null 2>&1 || { \
		echo "uv is not installed — see https://docs.astral.sh/uv/getting-started/installation/"; \
		exit 1; }
	cd $(BACKEND) && uv venv && uv pip install -e ".[dev]"
	cd $(FRONTEND) && npm ci
	@echo
	@echo "Next: cp backend/.env.example backend/.env, put your OPENAI_API_KEY in it,"
	@echo "      then make up-backend && make migrate && make doctor"

dev-backend: ## Run the API natively with reload (http://localhost:8000/docs)
	cd $(BACKEND) && .venv/bin/uvicorn src.main:app --reload --port 8000 $(ARGS)

dev-worker: ## Run the arq worker natively, reloading on change (analyses execute here)
	# --watch matters: every node of the analysis pipeline runs in this process, not in
	# the API, so without it each edit to a ratio or a prompt needs a manual restart.
	cd $(BACKEND) && .venv/bin/arq --watch src src.worker.WorkerSettings $(ARGS)

dev-frontend: ## Run the Next dev server natively (http://localhost:3000)
	cd $(FRONTEND) && npm run dev

migrate: ## Apply database migrations (alembic upgrade head)
	cd $(BACKEND) && .venv/bin/alembic upgrade head $(ARGS)

costs: ## Estimate cost per analysis from your own runs (make costs ARGS=--compare)
	@cd $(BACKEND) && .venv/bin/python scripts/costs.py $(ARGS)

doctor: ## Preflight: config, postgres, redis, the model provider, network, corpus
	@# Silent recipe: `make doctor ARGS=--json` has to be pipeable into jq.
	@cd $(BACKEND) && $(PY) scripts/doctor.py $(ARGS)

test: ## Run the backend test suite
	cd $(BACKEND) && $(PY) -m pytest tests/ -q $(ARGS)

lint: ## ruff (backend) + eslint and tsc (frontend)
	cd $(BACKEND) && .venv/bin/ruff check src tests scripts
	cd $(FRONTEND) && npm run lint
	cd $(FRONTEND) && npx --no-install tsc --noEmit

reset-quota: ## Clear anonymous run counters and today's spend (dev only, keeps analyses)
	cd $(BACKEND) && .venv/bin/python scripts/reset_quota.py $(ARGS)

seed: ## Pre-build the retrieval corpus for ~20 popular tickers
	cd $(BACKEND) && $(PY) scripts/seed_index.py --popular $(ARGS)

dev: ## Everything in docker with hot reload — no Python, Node or Postgres on your host
	docker compose -f docker-compose.dev.yml up --build

dev-down: ## Stop the containerised dev stack (named volumes, and so your data, stay)
	docker compose -f docker-compose.dev.yml down

dev-logs: ## Follow the dev stack logs (make dev-logs ARGS=worker)
	docker compose -f docker-compose.dev.yml logs -f $(ARGS)

dev-shell: ## Open a shell in the dev api container (make dev-shell ARGS=worker)
	docker compose -f docker-compose.dev.yml exec $(or $(ARGS),api) sh

up: ## Start the whole stack in docker (db, redis, api, worker, web)
	$(COMPOSE) up -d --build $(ARGS)
	@echo "api http://localhost:8000/docs   web http://localhost:3000"

down: ## Stop every stack. Containers go, named volumes (your data) stay
	$(COMPOSE) down $(ARGS)
	@# The per-service files are separate compose projects, so the root `down` does
	@# not reach them. Stopping something that was never started is a no-op.
	-@cd $(BACKEND) && $(COMPOSE) down 2>/dev/null
	-@cd $(FRONTEND) && $(COMPOSE) down 2>/dev/null

logs: ## Follow the logs of the whole stack (make logs ARGS=api)
	$(COMPOSE) logs -f --tail=100 $(ARGS)

up-backend: ## Start only backend/docker-compose.yml (db, redis, api, worker)
	cd $(BACKEND) && $(COMPOSE) up -d --build $(ARGS)

up-frontend: ## Start only frontend/docker-compose.yml (the Next server)
	cd $(FRONTEND) && $(COMPOSE) up -d --build $(ARGS)

clean: ## Delete build artefacts and caches (never the venv, packages or data)
	-find $(BACKEND) -name '__pycache__' -type d -not -path '*/.venv/*' -prune -exec rm -rf {} +
	-rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.ruff_cache $(BACKEND)/.coverage
	-rm -rf $(FRONTEND)/.next $(FRONTEND)/tsconfig.tsbuildinfo
	@echo "Kept: backend/.venv, frontend/node_modules, docker volumes."
