from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from agents_service.agents import service as agent_service
from agents_service.agents.schema import AgentOut
from agents_service.core.deps import AuthContext, get_current_auth
from agents_service.transcriber.schema import TranscriberSettingsUpdate

router = APIRouter(prefix="/agents", tags=["agents:transcriber"])


@router.patch("/{agent_id}/transcriber", response_model=SuccessResponse[AgentOut])
async def update_transcriber(
    agent_id: PydanticObjectId,
    payload: TranscriberSettingsUpdate,
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    agent, config = await agent_service.update_section(agent_id, auth, "transcriber", payload.model_dump(exclude_unset=True))
    return success_response(message="Agent transcriber updated", data=agent_service.to_out(agent, config))
