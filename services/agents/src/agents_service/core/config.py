from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "agents-service"
    # "development" is the only value that enables the auto-reloader (see
    # agents_service.main) — anything else (production, staging, ...) runs
    # without it, so reload can't be switched on in prod by mistake.
    environment: str = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"  # noqa: S104 - intentional: this is a container-facing service, not a laptop-only tool
    port: int = 8002
    # Ignored outside production (reload mode is always single-process).
    workers: int = 1

    # Mongo
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "bolotext_agents"

    # Identity is resolved by calling the Users service's internal
    # introspection endpoint (POST /api/v1/internal/introspect) rather than
    # decoding JWTs locally — see agents_service.core.http_client.
    users_service_url: str = "http://localhost:8001"
    internal_api_key: str = "change-me-internal-key"
    introspect_timeout_seconds: float = 5.0

    # Provider/model registry cache TTL (in-process cache; the seed data
    # itself is code, not a DB collection — see agents_service.providers).
    provider_cache_ttl_seconds: float = 300.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
