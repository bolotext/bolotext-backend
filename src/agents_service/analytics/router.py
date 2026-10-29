from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from agents_service.agents import service as agent_service
from agents_service.agents.schema import AgentOut
from agents_service.analytics.schema import AnalyticsSettingsUpdate
from agents_service.core.deps import AuthContext, get_current_auth

router = APIRouter(prefix="/agents", tags=["agents:analytics"])


@router.patch(
    "/{agent_id}/analytics",
    response_model=SuccessResponse[AgentOut],
    summary="Update an agent's analytics settings",
)
async def update_analytics(
    agent_id: PydanticObjectId,
    payload: AnalyticsSettingsUpdate,
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    """Updates the agent's `development` environment with the call
    analytics settings supplied in the payload — call disposition
    classification, post-call structured-data extraction, and the
    post-call-trigger webhook. Only fields present in the payload are
    changed; omitted fields keep their current value. The post-call-trigger
    webhook can also be managed on its own via
    `PATCH /agents/{agent_id}/post-call-trigger`.

    **Auth:** Bearer JWT required; the caller must own the agent.

    **Errors:**
    - `NOT_FOUND` — no agent with this ID exists for the caller.
    - `UNAUTHORIZED` — missing or invalid bearer token.
    - `UNPROCESSABLE_ENTITY` — the merged section fails validation.
    """
    agent, config = await agent_service.update_section(agent_id, auth, "analytics", payload.model_dump(exclude_unset=True))
    return success_response(message="Agent analytics updated", data=agent_service.to_out(agent, config))
