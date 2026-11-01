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
    port: int = 8000
    # Ignored outside production (reload mode is always single-process).
    workers: int = 1

    # Mongo
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "bolotext"

    # Provider/model registry cache TTL (in-process cache; the seed data
    # itself is code, not a DB collection — see agents_service.providers).
    provider_cache_ttl_seconds: float = 300.0

    # WhatsApp Business messaging. Twilio credentials and sender settings are
    # stored per organization in the DB (see agents_service.whatsapp.service,
    # edited from the UI) — only platform-wide tuning lives here.
    whatsapp_max_csv_rows: int = 5000
    whatsapp_send_concurrency: int = 5
    whatsapp_send_delay_ms: int = 100

    # LiveKit — used to mint web-call tokens (same project the voice agent worker connects to).
    livekit_url: str | None = None
    livekit_api_key: str | None = None
    livekit_api_secret: str | None = None
    # Telephony: the project's SIP URI (the provider's *origination* target).
    livekit_sip_uri: str | None = None
    # Rented LiveKit numbers are billed to the project, so an organization's Admin may hold only a few (Super Admins: no cap).
    phone_numbers_max_per_org: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
