from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from agents_service.agents import service as agent_service
from agents_service.agents.schema import AgentOut
from agents_service.core.deps import AuthContext, get_current_auth
from agents_service.precall_variables.schema import PreCallVariablesUpdate

router = APIRouter(prefix="/agents", tags=["agents:precall-variables"])


@router.put("/{agent_id}/pre-call-variables", response_model=SuccessResponse[AgentOut])
async def update_pre_call_variables(
    agent_id: PydanticObjectId, payload: PreCallVariablesUpdate, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    agent, config = await agent_service.update_pre_call_variables(
        agent_id, auth, payload.pre_call_variables, payload.pre_call_variables_enabled
    )
    return success_response(message="Pre-call variables updated", data=agent_service.to_out(agent, config))
