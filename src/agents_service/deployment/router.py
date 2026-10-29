from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from agents_service.agents import service as agent_service
from agents_service.agents.schema import AgentOut
from agents_service.core.deps import AuthContext, get_current_auth
from agents_service.deployment.schema import DeploymentSettingsUpdate

router = APIRouter(prefix="/agents", tags=["agents:deployment"])


@router.patch(
    "/{agent_id}/deployment",
    response_model=SuccessResponse[AgentOut],
    summary="Update an agent's deployment/channel settings",
)
async def update_deployment(
    agent_id: PydanticObjectId,
    payload: DeploymentSettingsUpdate,
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    """Updates the agent's `development` environment with the deployment
    settings supplied in the payload — which channels (inbound/outbound
    calling, chat widget) are enabled and which origins may embed the chat
    widget. Only fields present in the payload are changed; omitted fields
    keep their current value.

    **Auth:** Bearer JWT required; the caller must own the agent.

    **Errors:**
    - `NOT_FOUND` — no agent with this ID exists for the caller.
    - `UNAUTHORIZED` — missing or invalid bearer token.
    - `UNPROCESSABLE_ENTITY` — the merged section fails validation.
    """
    agent, config = await agent_service.update_section(agent_id, auth, "deployment", payload.model_dump(exclude_unset=True))
    return success_response(message="Agent deployment settings updated", data=agent_service.to_out(agent, config))
