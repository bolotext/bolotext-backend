.PHONY: install seed run run-prod \
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
