import re

from beanie import PydanticObjectId  # noqa: F401  (kept for parity with sibling routers)
from common.errors import ForbiddenError, UnprocessableEntityError
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends, Path, Query

from agents_service.core.deps import AuthContext, get_current_auth
from agents_service.usage import service
from agents_service.usage.schema import (
    ModelPriceIn,
    ModelPriceOut,
    OrgUsageDetail,
    PricingList,
    UsageOverview,
    UsageSettingsIn,
    UsageSettingsOut,
)

router = APIRouter(prefix="/admin/usage", tags=["admin:usage"])

_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


async def require_super_admin(auth: AuthContext = Depends(get_current_auth)) -> AuthContext:
    if not auth.is_super_admin:
        raise ForbiddenError("Only a Super Admin can view platform usage")
    return auth


def _day(v: str | None, name: str) -> str | None:
    if v is not None and not _DAY.match(v):
        raise UnprocessableEntityError(f"{name} must be YYYY-MM-DD")
    return v


@router.get("", response_model=SuccessResponse[UsageOverview], summary="Platform usage and cost per organization")
async def overview(
    day_from: str | None = Query(None, alias="from", description="First UTC day, YYYY-MM-DD."),
    day_to: str | None = Query(None, alias="to", description="Last UTC day (inclusive), YYYY-MM-DD."),
    include_test: bool = Query(False, description="Include calls made from the builder's Test call."),
    _: AuthContext = Depends(require_super_admin),
) -> dict:
    """STT / LLM / TTS usage and cost for every organization, read from the
    `token_usage` rollup (not from call logs). Cost uses the prices in
    `/admin/usage/pricing`; models without a price are left out of the cost
    and flagged `has_unpriced`.

    **Auth:** Super Admin only (`FORBIDDEN` otherwise)."""
    return success_response(data=await service.overview(_day(day_from, "from"), _day(day_to, "to"), include_test))


@router.get("/pricing", response_model=SuccessResponse[PricingList], summary="Per-model prices")
async def get_pricing(_: AuthContext = Depends(require_super_admin)) -> dict:
    """Every model seen in usage (with `priced=false` if no price is set yet) plus priced ones. Super Admin only."""
    return success_response(data=await service.list_pricing())


@router.put("/pricing", response_model=SuccessResponse[ModelPriceOut], summary="Set a model's price")
async def put_pricing(payload: ModelPriceIn, _: AuthContext = Depends(require_super_admin)) -> dict:
    """Create or replace the price of one `(kind, provider_id, model_id)`. Takes effect immediately for all
    dashboards, past usage included (usage is stored as units, not money). Super Admin only."""
    return success_response(message="Price saved", data=await service.upsert_price(payload))


@router.put("/settings", response_model=SuccessResponse[UsageSettingsOut], summary="Set the USD to INR display rate")
async def put_settings(payload: UsageSettingsIn, _: AuthContext = Depends(require_super_admin)) -> dict:
    """Rupees per US dollar. Only used to show ₹ next to $ on the dashboard; prices stay in USD. Super Admin only."""
    return success_response(message="Rate saved", data=await service.set_rate(payload.usd_to_inr))


@router.get("/organizations/{org_id}", response_model=SuccessResponse[OrgUsageDetail], summary="One organization's usage per agent and model")
async def organization_usage(
    org_id: str = Path(description="The organization's id."),
    day_from: str | None = Query(None, alias="from"),
    day_to: str | None = Query(None, alias="to"),
    include_test: bool = Query(False),
    _: AuthContext = Depends(require_super_admin),
) -> dict:
    """Totals, per-agent and per-provider/model usage and cost for one organization. Super Admin only."""
    return success_response(data=await service.org_detail(org_id, _day(day_from, "from"), _day(day_to, "to"), include_test))
