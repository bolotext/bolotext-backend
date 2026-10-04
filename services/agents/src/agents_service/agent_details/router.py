from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends, Path

from agents_service.agent_details.schema import AgentDetailsUpdate
from agents_service.agents import service as agent_service
from agents_service.agents.schema import AgentOut
from agents_service.core.deps import AuthContext, get_current_auth

router = APIRouter(prefix="/agents", tags=["agents:agent-details"])


@router.patch(
    "/{agent_id}/agent-details",
    response_model=SuccessResponse[AgentOut],
    summary="Update an agent's details",
)
async def update_agent_details(
    agent_id: PydanticObjectId = Path(description="The agent's id."),
    payload: AgentDetailsUpdate = ...,
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    """Partially updates the "Agent Details" tab (name, description, region,
    timezone, bot type) on the agent's `development` environment. Only the
    fields supplied in the request body are changed; omitted fields keep
    their current value. Does not touch configured languages — use
    `PUT /agents/{agent_id}/languages` for that.

    **Auth:** bearer JWT required; caller must own the agent.

    **Errors:** `NOT_FOUND` if no such agent exists, or it belongs to
    another caller; `UNPROCESSABLE_ENTITY` if the resulting details fail a
    save-time business rule.
    """
    # Split across two documents under the hood (name/description on the
    # Agent identity doc, the rest on AgentConfig) — see
    # agents.service.update_agent_details. The tab's own API shape doesn't
    # change.
    agent, config = await agent_service.update_agent_details(agent_id, auth, payload.model_dump(exclude_unset=True))
    return success_response(message="Agent details updated", data=agent_service.to_out(agent, config))
