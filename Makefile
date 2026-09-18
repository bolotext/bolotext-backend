.PHONY: install test test-agents seed run-users run-gateway run-agents docker-build docker-up docker-down docker-restart

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

run-users:
	@echo 'Running the Users service locally on :8001 (expects a reachable MongoDB, see services/users/.env)'
	cd services/users && uv run python main.py serve

run-gateway:
	@echo 'Running the API Gateway locally on :8000 (expects the Users service reachable, see services/api-gateway/.env)'
	cd services/api-gateway && uv run python main.py

run-agents:
	@echo 'Running the Agents service locally on :8002 (expects a reachable MongoDB and the Users service, see services/agents/.env)'
	cd services/agents && uv run python main.py

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
