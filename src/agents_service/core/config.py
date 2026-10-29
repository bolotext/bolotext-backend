from functools import lru_cache

from pydantic import Field
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
    mongo_db_name: str = Field("bolotext_agents", validation_alias="AGENTS_MONGO_DB_NAME")

    # Identity is resolved in-process by the Users service's introspection
    # logic rather than decoding JWTs locally — see agents_service.core.http_client.
    internal_api_key: str = "change-me-internal-key"

    # Provider/model registry cache TTL (in-process cache; the seed data
    # itself is code, not a DB collection — see agents_service.providers).
    provider_cache_ttl_seconds: float = 300.0

    # WhatsApp Business messaging. Twilio credentials and sender settings are
    # stored per organization in the DB (see agents_service.whatsapp.service,
    # edited from the UI) — only platform-wide tuning and the key that encrypts
    # the stored auth token live here. If WHATSAPP_ENCRYPTION_KEY (a Fernet key)
    # is unset, a key is derived from INTERNAL_API_KEY; set it explicitly in
    # production so rotating the internal key can't orphan stored tokens.
    whatsapp_encryption_key: str = ""
    whatsapp_max_csv_rows: int = 5000
    whatsapp_send_concurrency: int = 5
    whatsapp_send_delay_ms: int = 100


@lru_cache
def get_settings() -> Settings:
    return Settings()
