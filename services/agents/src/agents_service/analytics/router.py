from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from agents_service.agents import service as agent_service
from agents_service.agents.schema import AgentOut
from agents_service.analytics.schema import AnalyticsSettingsUpdate
from agents_service.core.deps import AuthContext, get_current_auth

router = APIRouter(prefix="/agents", tags=["agents:analytics"])


@router.patch("/{agent_id}/analytics", response_model=SuccessResponse[AgentOut])
async def update_analytics(
    agent_id: PydanticObjectId,
    payload: AnalyticsSettingsUpdate,
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    agent, config = await agent_service.update_section(agent_id, auth, "analytics", payload.model_dump(exclude_unset=True))
    return success_response(message="Agent analytics updated", data=agent_service.to_out(agent, config))
