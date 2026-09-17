from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "api-gateway"
    log_level: str = "INFO"

    # Upstream service base URLs. Only `users_service_url` is required today;
    # `agents_service_url` is unset until that service actually exists, and
    # routes under its prefix 502 until it's configured.
    users_service_url: str = "http://localhost:8001"
    agents_service_url: str | None = None

    upstream_timeout_seconds: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
