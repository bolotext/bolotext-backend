# Build context is the repo root (uv workspace): `docker build -f services/agents/Dockerfile .`
# NOTE: this service is a health-check stub only — see agents_service/app.py.
FROM python:3.12-slim AS base
WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

ARG UV_VERSION=0.7.12
RUN curl -fsSL https://astral.sh/uv/$UV_VERSION/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

COPY pyproject.toml uv.lock /app/
COPY libs/common/pyproject.toml /app/libs/common/pyproject.toml
COPY services/agents/pyproject.toml /app/services/agents/pyproject.toml
COPY services/users/pyproject.toml /app/services/users/pyproject.toml
COPY services/api-gateway/pyproject.toml /app/services/api-gateway/pyproject.toml

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-workspace --package agents-service --compile-bytecode

COPY libs/common/src /app/libs/common/src
COPY services/agents/src /app/services/agents/src
COPY services/agents/main.py /app/services/agents/main.py
COPY services/agents/entrypoint.sh /app/services/agents/entrypoint.sh

RUN chmod +x /app/services/agents/entrypoint.sh
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/services/agents/src:/app/libs/common/src"

WORKDIR /app/services/agents
EXPOSE 8002
ENTRYPOINT ["./entrypoint.sh"]
