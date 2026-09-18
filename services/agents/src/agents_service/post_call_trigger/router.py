from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from agents_service.agents import service as agent_service
from agents_service.agents.schema import AgentOut
from agents_service.core.deps import AuthContext, get_current_auth
from agents_service.post_call_trigger.schema import PostCallTriggerSettingsUpdate

router = APIRouter(prefix="/agents", tags=["agents:post-call-trigger"])


@router.patch("/{agent_id}/post-call-trigger", response_model=SuccessResponse[AgentOut])
async def update_post_call_trigger_config(
    agent_id: PydanticObjectId, payload: PostCallTriggerSettingsUpdate, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    agent, config = await agent_service.update_post_call_trigger(agent_id, auth, payload.model_dump(exclude_unset=True))
    return success_response(message="Post-call trigger configuration updated", data=agent_service.to_out(agent, config))
