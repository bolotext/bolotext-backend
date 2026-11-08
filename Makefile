.PHONY: install seed run run-prod run-frontend run-agent runall \
	docker-build docker-up docker-down docker-restart

install:
	@echo 'Installing dependencies with uv'
	uv sync

seed:
	@echo 'Seeding roles and the bootstrap Super Admin'
	uv run python src/main.py seed

# Dev mode (default: ENVIRONMENT=development, from .env) — uvicorn runs with
# auto-reload, always single-process.
run:
	@echo 'Running the backend locally in dev mode (reload on; expects a reachable MongoDB, see .env)'
	uv run python src/main.py

# Prod mode without Docker (ENVIRONMENT=production forces reload off; set
# WORKERS to override the worker count, default 1).
# For an actual deployment, prefer `make docker-up` (see docker-compose.yml).
run-prod:
	@echo 'Running the backend locally in production mode (no reload; WORKERS from .env)'
	ENVIRONMENT=production uv run python src/main.py

# Frontend lives in the sibling repo; override with FRONTEND_DIR=... if elsewhere.
FRONTEND_DIR ?= ../bolotext-frontend

run-frontend:
	@echo 'Running the frontend dev server from $(FRONTEND_DIR)'
	cd $(FRONTEND_DIR) && npm run dev

# Backend + frontend + agent together; Ctrl+C stops all three.
runall:
	@echo 'Running the backend, the frontend and the agent (Ctrl+C stops all)'
	@trap 'kill $$(jobs -p) 2>/dev/null' INT TERM EXIT; \
	$(MAKE) run & \
	$(MAKE) run-frontend & \
	$(MAKE) run-agent & \
	wait

# Agent runtime lives in the sibling repo; override with AGENT_DIR=... if elsewhere.
AGENT_DIR ?= ../bolotext-agent

run-agent:
	@echo 'Running bolotext-agent from $(AGENT_DIR)'
	cd $(AGENT_DIR) && $(MAKE) run

docker-build:
	@echo 'Building the backend image'
	docker compose build

docker-up:
	@echo 'Starting the backend'
	docker compose up -d

docker-down:
	@echo 'Stopping the backend'
	docker compose down

docker-restart: docker-down docker-build docker-up
