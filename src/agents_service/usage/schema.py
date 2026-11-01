from typing import Literal

from pydantic import BaseModel, Field

Kind = Literal["stt", "llm", "tts"]


class Totals(BaseModel):
    calls: int = 0
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    audio_seconds: float = 0
    characters: int = 0


class CostLine(BaseModel):
    """Usage and cost of one provider model."""

    kind: Kind
    provider_id: str
    model_id: str
    usage: Totals
    cost: float | None = Field(None, description="None when no price is set for this model.")


class KindSummary(BaseModel):
    kind: Kind
    usage: Totals
    cost: float = Field(0, description="Sum of the priced models only.")
    unpriced_models: int = 0


class UsageSummary(BaseModel):
    kinds: list[KindSummary]
    cost: float
    has_unpriced: bool


class OrgUsageRow(UsageSummary):
    org_id: str
    org_name: str


class DailyPoint(BaseModel):
    day: str
    cost: float
    calls: int


class UsageOverview(BaseModel):
    currency: str = "USD"
    usd_to_inr: float | None = None
    total: UsageSummary
    organizations: list[OrgUsageRow]
    daily: list[DailyPoint]


class OrgUsageDetail(BaseModel):
    currency: str = "USD"
    usd_to_inr: float | None = None
    org_id: str
    org_name: str
    total: UsageSummary
    models: list[CostLine]
    daily: list[DailyPoint]


class ModelPriceIn(BaseModel):
    kind: Kind
    provider_id: str = Field(min_length=1, max_length=100)
    model_id: str = Field(min_length=1, max_length=200)
    currency: str = "USD"
    input_per_million: float | None = Field(None, ge=0)
    cached_input_per_million: float | None = Field(None, ge=0)
    output_per_million: float | None = Field(None, ge=0)
    per_minute: float | None = Field(None, ge=0)
    per_million_chars: float | None = Field(None, ge=0)


class ModelPriceOut(ModelPriceIn):
    priced: bool = True


class UsageSettingsIn(BaseModel):
    usd_to_inr: float = Field(gt=0, le=10000, description="Rupees per 1 US dollar.")


class UsageSettingsOut(BaseModel):
    usd_to_inr: float | None = None


class PricingList(BaseModel):
    usd_to_inr: float | None = None
    prices: list[ModelPriceOut] = Field(description="Every model seen in usage, plus any priced model; `priced=False` rows need a price.")
