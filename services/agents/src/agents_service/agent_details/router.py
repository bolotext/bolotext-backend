from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from agents_service.agent_details.schema import AgentDetailsUpdate
from agents_service.agents import service as agent_service
from agents_service.agents.schema import AgentOut
from agents_service.core.deps import AuthContext, get_current_auth

router = APIRouter(prefix="/agents", tags=["agents:agent-details"])


@router.patch("/{agent_id}/agent-details", response_model=SuccessResponse[AgentOut])
async def update_agent_details(
    agent_id: PydanticObjectId,
    payload: AgentDetailsUpdate,
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    # Split across two documents under the hood (name/description on the
    # Agent identity doc, the rest on AgentConfig) — see
    # agents.service.update_agent_details. The tab's own API shape doesn't
    # change.
    agent, config = await agent_service.update_agent_details(agent_id, auth, payload.model_dump(exclude_unset=True))
    return success_response(message="Agent details updated", data=agent_service.to_out(agent, config))
