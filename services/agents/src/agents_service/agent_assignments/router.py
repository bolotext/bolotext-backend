from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from agents_service.agent_assignments.schema import AssignmentCreate
from agents_service.agents import service as agent_service
from agents_service.core.deps import AuthContext, get_current_auth

router = APIRouter(prefix="/agents", tags=["agents:assignments"])


@router.post("/{agent_id}/assignments", response_model=SuccessResponse[list[str]])
async def assign_agent(
    agent_id: PydanticObjectId, payload: AssignmentCreate, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    assignees = await agent_service.assign_agent(agent_id, auth, payload.user_id)
    return success_response(code=201, message="Agent assigned", data=assignees)


@router.get("/{agent_id}/assignments", response_model=SuccessResponse[list[str]])
async def list_agent_assignments(agent_id: PydanticObjectId, auth: AuthContext = Depends(get_current_auth)) -> dict:
    assignees = await agent_service.list_agent_assignees(agent_id, auth)
    return success_response(data=assignees)


@router.delete("/{agent_id}/assignments/{user_id}", response_model=SuccessResponse[list[str]])
async def unassign_agent(
    agent_id: PydanticObjectId, user_id: str, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    assignees = await agent_service.unassign_agent(agent_id, auth, user_id)
    return success_response(message="Agent unassigned", data=assignees)
