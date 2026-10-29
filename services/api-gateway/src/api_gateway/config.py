from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "api-gateway"
    # "development" is the only value that enables the auto-reloader (see
    # api_gateway.main) — anything else (production, staging, ...) runs
    # without it, so reload can't be switched on in prod by mistake.
    environment: str = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"  # noqa: S104 - intentional: this is a container-facing service, not a laptop-only tool
    port: int = 8000
    # Ignored outside production (reload mode is always single-process).
    workers: int = 1

    # Upstream service base URLs. Only `users_service_url` is required today;
    # `agents_service_url` is unset until that service actually exists, and
    # routes under its prefix 502 until it's configured.
    users_service_url: str = "http://localhost:8001"
    agents_service_url: str | None = None

    upstream_timeout_seconds: float = 30.0

    # Optional: pin the public URL this gateway is reachable at (e.g.
    # https://api.example.com). By default it's derived per request from
    # X-Forwarded-Proto/Host (or Host) and passed to upstream services in
    # `X-Public-Base-Url` — used for callbacks such as Twilio's delivery status.
    public_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
