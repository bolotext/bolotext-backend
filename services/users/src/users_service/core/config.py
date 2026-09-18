from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "users-service"
    # "development" is the only value that enables the auto-reloader (see
    # users_service.main) — anything else (production, staging, ...) runs
    # without it, so reload can't be switched on in prod by mistake.
    environment: str = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"  # noqa: S104 - intentional: this is a container-facing service, not a laptop-only tool
    port: int = 8001
    # Ignored outside production (reload mode is always single-process).
    workers: int = 1

    # Mongo
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "bolotext_users"

    # JWT (this secret is shared with the API Gateway / other services that
    # need to verify tokens this service issues; keep it identical across them)
    jwt_secret: str = "change-me-in-env"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    # Internal service-to-service auth (for the token introspection endpoint)
    internal_api_key: str = "change-me-internal-key"

    # Rate limiting
    login_rate_limit: str = "5/minute"

    # Bootstrap super admin (used only by the idempotent seed script)
    bootstrap_super_admin_email: str | None = None
    bootstrap_super_admin_password: str | None = None
    bootstrap_super_admin_name: str = "Super Admin"


@lru_cache
def get_settings() -> Settings:
    return Settings()
