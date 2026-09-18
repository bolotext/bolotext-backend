from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from agents_service.agents import service as agent_service
from agents_service.agents.schema import AgentOut
from agents_service.core.deps import AuthContext, get_current_auth
from agents_service.languages.schema import LanguagesUpdate

router = APIRouter(prefix="/agents", tags=["agents:languages"])


@router.put("/{agent_id}/languages", response_model=SuccessResponse[AgentOut])
async def update_languages(
    agent_id: PydanticObjectId, payload: LanguagesUpdate, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    agent, config = await agent_service.update_languages(agent_id, auth, payload.languages)
    return success_response(message="Agent languages updated", data=agent_service.to_out(agent, config))
