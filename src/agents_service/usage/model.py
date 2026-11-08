from datetime import datetime, timezone
from typing import Literal

from beanie import Document
from pydantic import Field
from pymongo import IndexModel

Kind = Literal["stt", "llm", "tts"]


class UsageRollup(Document):
    """Running totals of provider usage, one document per
    (org, UTC day, kind, provider, model, test) — deliberately not per agent,
    so the collection stays small however many agents an organization has. The voice runtime reports each call (`POST /call-logs/usage`) and that `$inc`s
    the matching document (creating it on first use), so the Usage dashboard
    reads a few small documents instead of scanning every call log.

    Only raw units are stored, never money: prices change, so cost is computed
    at read time from `ModelPrice` (see usage.service)."""

    org_id: str
    day: str  # "YYYY-MM-DD", UTC
    kind: Kind
    provider_id: str
    model_id: str
    test: bool = False

    calls: int = 0
    input_tokens: int = 0  # llm: prompt tokens, including cached ones
    cached_tokens: int = 0  # llm: the cached part of input_tokens
    output_tokens: int = 0  # llm
    audio_seconds: float = 0  # stt
    characters: int = 0  # tts
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "token_usage"
        indexes = [
            IndexModel(
                [("org_id", 1), ("day", 1), ("kind", 1), ("provider_id", 1), ("model_id", 1), ("test", 1)],
                unique=True,
            ),
            IndexModel([("day", 1), ("org_id", 1)]),
        ]


class ModelPrice(Document):
    """What a provider model costs. Maintained by a Super Admin; nothing is
    seeded because prices must come from the provider contracts.

    llm: `input_per_million` / `cached_input_per_million` / `output_per_million` (per 1M tokens)
    stt: `per_minute` (per audio minute)
    tts: `per_million_chars` (per 1M characters)"""

    kind: Kind
    provider_id: str
    model_id: str
    currency: str = "USD"
    input_per_million: float | None = None
    cached_input_per_million: float | None = None
    output_per_million: float | None = None
    per_minute: float | None = None
    per_million_chars: float | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "model_prices"
        indexes = [IndexModel([("kind", 1), ("provider_id", 1), ("model_id", 1)], unique=True)]


class UsageSettings(Document):
    """Single document (key="default"): display settings for the usage dashboard."""

    key: str = "default"
    # Rupees per US dollar, used only to show amounts in INR next to USD; never applied to stored prices.
    usd_to_inr: float | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "usage_settings"
        indexes = [IndexModel("key", unique=True)]
