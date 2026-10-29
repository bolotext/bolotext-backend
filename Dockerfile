# Single image running the whole backend (Users + Agents) as one service.
# Build context is the repo root: `docker build .`
FROM python:3.12-slim AS base
WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

ARG UV_VERSION=0.7.12
RUN curl -fsSL https://astral.sh/uv/$UV_VERSION/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

COPY pyproject.toml uv.lock /app/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --compile-bytecode

COPY src /app/src

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV PYTHONUNBUFFERED=1

# Production by default; config comes from the environment (no .env in the image).
ENV ENVIRONMENT=production
ENV PORT=7860

# Hugging Face Spaces runs containers as uid 1000.
RUN useradd -m -u 1000 app
USER app

EXPOSE 7860
CMD ["python", "src/main.py"]
