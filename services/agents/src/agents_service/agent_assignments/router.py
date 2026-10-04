from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends, Path

from agents_service.agent_assignments.schema import AssignmentCreate
from agents_service.agents import service as agent_service
from agents_service.core.deps import AuthContext, get_current_auth

router = APIRouter(prefix="/agents", tags=["agents:assignments"])


@router.post(
    "/{agent_id}/assignments",
    response_model=SuccessResponse[list[str]],
    summary="Assign an agent to a user",
)
async def assign_agent(
    agent_id: PydanticObjectId, payload: AssignmentCreate, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    """Grants a Developer visibility into this agent — a Developer can only
    see/act on agents explicitly assigned to them; Admin and QA already have
    full/view-only access and don't need an assignment. Assigning a user who
    is already assigned is a no-op. Returns the full, updated list of
    assignee user ids.

    **Auth:** bearer JWT required; caller must be an Admin (or Super Admin)
    with access to this agent.

    **Errors:**
    - `NOT_FOUND` — no agent with this ID exists for the caller.
    - `FORBIDDEN` — caller isn't an Admin/Super Admin.
    """
    assignees = await agent_service.assign_agent(agent_id, auth, payload.user_id)
    return success_response(code=201, message="Agent assigned", data=assignees)


@router.get(
    "/{agent_id}/assignments",
    response_model=SuccessResponse[list[str]],
    summary="List an agent's assigned users",
)
async def list_agent_assignments(agent_id: PydanticObjectId, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Returns the user ids currently assigned to this agent.

    **Auth:** bearer JWT required; caller must be an Admin (or Super Admin)
    with access to this agent.

    **Errors:**
    - `NOT_FOUND` — no agent with this ID exists for the caller.
    - `FORBIDDEN` — caller isn't an Admin/Super Admin.
    """
    assignees = await agent_service.list_agent_assignees(agent_id, auth)
    return success_response(data=assignees)


@router.delete(
    "/{agent_id}/assignments/{user_id}",
    response_model=SuccessResponse[list[str]],
    summary="Unassign a user from an agent",
)
async def unassign_agent(
    agent_id: PydanticObjectId,
    user_id: str = Path(..., description="ID of the user to remove from this agent's assignees."),
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    """Revokes a Developer's assignment to this agent, removing their
    visibility into it. Returns the full, updated list of assignee user ids.

    **Auth:** bearer JWT required; caller must be an Admin (or Super Admin)
    with access to this agent.

    **Errors:**
    - `NOT_FOUND` — no agent with this ID exists for the caller, or the
      given `user_id` has no assignment on this agent.
    - `FORBIDDEN` — caller isn't an Admin/Super Admin.
    """
    assignees = await agent_service.unassign_agent(agent_id, auth, user_id)
    return success_response(message="Agent unassigned", data=assignees)
