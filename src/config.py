from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "bolotext-backend"
    # "development" is the only value that enables the auto-reloader (see
    # main.py) — anything else (production, staging, ...) runs without it, so
    # reload can't be switched on in prod by mistake.
    environment: str = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"  # noqa: S104 - intentional: this is a container-facing service, not a laptop-only tool
    # 7860 is the port Hugging Face Spaces exposes.
    port: int = 7860
    # Ignored outside production (reload mode is always single-process).
    workers: int = 1

    # Optional: pin the public URL this service is reachable at (e.g.
    # https://api.example.com). By default it's derived per request from
    # X-Forwarded-Proto/Host (or Host) — used for callbacks such as Twilio's
    # delivery status.
    public_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
