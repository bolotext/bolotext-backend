from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from agents_service.agents import service as agent_service
from agents_service.agents.schema import AgentOut
from agents_service.core.deps import AuthContext, get_current_auth
from agents_service.dynamic_message.schema import DynamicMessageSettingsUpdate

router = APIRouter(prefix="/agents", tags=["agents:dynamic-message"])


@router.patch("/{agent_id}/dynamic-message", response_model=SuccessResponse[AgentOut])
async def update_dynamic_message_config(
    agent_id: PydanticObjectId, payload: DynamicMessageSettingsUpdate, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    agent, config = await agent_service.update_dynamic_message(agent_id, auth, payload.model_dump(exclude_unset=True))
    return success_response(message="Dynamic message configuration updated", data=agent_service.to_out(agent, config))
