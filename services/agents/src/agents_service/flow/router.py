from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends, Path

from agents_service.agents import service as agent_service
from agents_service.agents.schema import AgentOut
from agents_service.core.deps import AuthContext, get_current_auth
from agents_service.flow.schema import AgentFlowUpdate

router = APIRouter(prefix="/agents", tags=["agents:flow"])


@router.patch(
    "/{agent_id}/flow",
    response_model=SuccessResponse[AgentOut],
    summary="Update an agent's conversation flow",
)
async def update_flow(
    agent_id: PydanticObjectId = Path(description="The agent's id."),
    payload: AgentFlowUpdate = ...,
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    """Partially updates the "Flow" tab (agent type, drop-off scenarios, and
    an optional custom flow definition) on the agent's `development`
    environment. Only the fields supplied in the request body are changed.

    **Auth:** bearer JWT required; caller must own the agent.

    **Errors:** `NOT_FOUND` if no such agent exists, or it belongs to
    another caller; `UNPROCESSABLE_ENTITY` if the resulting flow fails a
    save-time business rule.
    """
    agent, config = await agent_service.update_section(agent_id, auth, "flow", payload.model_dump(exclude_unset=True))
    return success_response(message="Agent flow updated", data=agent_service.to_out(agent, config))
