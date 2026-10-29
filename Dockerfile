# Single image running Users + Agents + API Gateway (see run_all.py).
# Build context is the repo root (uv workspace): `docker build .`
FROM python:3.12-slim AS base
WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

ARG UV_VERSION=0.7.12
RUN curl -fsSL https://astral.sh/uv/$UV_VERSION/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Workspace metadata first (cache-friendly layer).
COPY pyproject.toml uv.lock /app/
COPY libs/common/pyproject.toml /app/libs/common/pyproject.toml
COPY services/users/pyproject.toml /app/services/users/pyproject.toml
COPY services/agents/pyproject.toml /app/services/agents/pyproject.toml
COPY services/api-gateway/pyproject.toml /app/services/api-gateway/pyproject.toml

# Third-party deps for every service; local packages are importable via PYTHONPATH below.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-workspace --all-packages --compile-bytecode

COPY libs/common/src /app/libs/common/src
COPY services/users/src /app/services/users/src
COPY services/agents/src /app/services/agents/src
COPY services/api-gateway/src /app/services/api-gateway/src
COPY run_all.py /app/run_all.py

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/services/users/src:/app/services/agents/src:/app/services/api-gateway/src:/app/libs/common/src"
ENV PYTHONUNBUFFERED=1

# Production by default; config comes from the environment (no .env in the image).
ENV ENVIRONMENT=production
ENV PORT=7860

# Hugging Face Spaces runs containers as uid 1000.
RUN useradd -m -u 1000 app
USER app

EXPOSE 7860
CMD ["python", "run_all.py"]
