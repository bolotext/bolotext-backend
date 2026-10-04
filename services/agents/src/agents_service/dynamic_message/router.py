from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from agents_service.agents import service as agent_service
from agents_service.agents.schema import AgentOut
from agents_service.core.deps import AuthContext, get_current_auth
from agents_service.dynamic_message.schema import DynamicMessageSettingsUpdate

router = APIRouter(prefix="/agents", tags=["agents:dynamic-message"])


@router.patch(
    "/{agent_id}/dynamic-message",
    response_model=SuccessResponse[AgentOut],
    summary="Update an agent's dynamic message configuration",
)
async def update_dynamic_message_config(
    agent_id: PydanticObjectId, payload: DynamicMessageSettingsUpdate, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    """Updates the agent's `development` environment with the dynamic
    message configuration supplied in the payload — an external API the
    agent calls mid-conversation to fetch live data (e.g. an order status)
    to speak back to the caller. Only fields present in the payload are
    changed; omitted fields keep their current value.

    **Auth:** Bearer JWT required; the caller must own the agent.

    **Errors:**
    - `NOT_FOUND` — no agent with this ID exists for the caller.
    - `UNAUTHORIZED` — missing or invalid bearer token.
    - `UNPROCESSABLE_ENTITY` — the merged section fails validation.
    """
    agent, config = await agent_service.update_dynamic_message(agent_id, auth, payload.model_dump(exclude_unset=True))
    return success_response(message="Dynamic message configuration updated", data=agent_service.to_out(agent, config))
