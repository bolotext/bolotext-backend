.PHONY: install test test-agents seed run-users run-gateway run-agents run-all \
	run-users-prod run-gateway-prod run-agents-prod \
	docker-build docker-up docker-down docker-restart

install:
	@echo 'Installing all workspace packages with uv'
	uv sync

test:
	@echo 'Running the Users service test suite'
	uv run --package users-service pytest services/users/tests

test-agents:
	@echo 'Running the Agents service test suite'
	uv run --package agents-service pytest services/agents/tests

seed:
	@echo 'Seeding roles and the bootstrap Super Admin (Users service)'
	cd services/users && uv run python main.py seed

# Dev mode (default: ENVIRONMENT=development, from each service's .env) —
# uvicorn runs with auto-reload, always single-process. Equivalent to
# `uvicorn <service>.app:app --host 0.0.0.0 --port <port> --reload`.
run-users:
	@echo 'Running the Users service locally on :8001 in dev mode (reload on; expects a reachable MongoDB, see services/users/.env)'
	cd services/users && uv run python main.py serve

run-gateway:
	@echo 'Running the API Gateway locally on :8000 in dev mode (reload on; expects the Users service reachable, see services/api-gateway/.env)'
	cd services/api-gateway && uv run python main.py

run-agents:
	@echo 'Running the Agents service locally on :8002 in dev mode (reload on; expects a reachable MongoDB and the Users service, see services/agents/.env)'
	cd services/agents && uv run python main.py

run-all:
	@echo 'Running Users (:8001), API Gateway (:8000) and Agents (:8002) locally in dev mode (Ctrl+C stops all)'
	@trap 'kill 0' INT TERM EXIT; \
	(cd services/users && uv run python main.py serve) & \
	(cd services/api-gateway && uv run python main.py) & \
	(cd services/agents && uv run python main.py) & \
	wait

# Prod mode without Docker (ENVIRONMENT=production forces reload off; set
# WORKERS to override the worker count, default 4). Equivalent to
# `uvicorn <service>.app:app --host 0.0.0.0 --port <port> --workers ${WORKERS:-4}`.
# For an actual deployment, prefer `make docker-up` (see docker-compose.yml).
run-users-prod:
	@echo 'Running the Users service locally on :8001 in production mode (no reload, $${WORKERS:-4} workers)'
	cd services/users && ENVIRONMENT=production uv run python main.py serve

run-gateway-prod:
	@echo 'Running the API Gateway locally on :8000 in production mode (no reload, $${WORKERS:-4} workers)'
	cd services/api-gateway && ENVIRONMENT=production uv run python main.py

run-agents-prod:
	@echo 'Running the Agents service locally on :8002 in production mode (no reload, $${WORKERS:-4} workers)'
	cd services/agents && ENVIRONMENT=production uv run python main.py

docker-build:
	@echo 'Building all service images'
	docker compose build

docker-up:
	@echo 'Starting mongo + all services'
	docker compose up -d

docker-down:
	@echo 'Stopping all services'
	docker compose down

docker-restart: docker-down docker-build docker-up
