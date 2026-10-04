from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from agents_service.agents import service as agent_service
from agents_service.agents.schema import AgentOut
from agents_service.core.deps import AuthContext, get_current_auth
from agents_service.post_call_trigger.schema import PostCallTriggerSettingsUpdate

router = APIRouter(prefix="/agents", tags=["agents:post-call-trigger"])


@router.patch(
    "/{agent_id}/post-call-trigger",
    response_model=SuccessResponse[AgentOut],
    summary="Update an agent's post-call trigger webhook",
)
async def update_post_call_trigger_config(
    agent_id: PydanticObjectId, payload: PostCallTriggerSettingsUpdate, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    """Updates the agent's `development` environment with the post-call
    trigger webhook settings supplied in the payload — an HTTP callback the
    platform invokes once a call ends. Only fields present in the payload
    are changed; omitted fields keep their current value. This is a
    dedicated shortcut for `AnalyticsSettings.post_call_trigger`, the same
    field also reachable via the broader
    `PATCH /agents/{agent_id}/analytics`.

    **Auth:** Bearer JWT required; the caller must own the agent.

    **Errors:**
    - `NOT_FOUND` — no agent with this ID exists for the caller.
    - `UNAUTHORIZED` — missing or invalid bearer token.
    - `UNPROCESSABLE_ENTITY` — the merged configuration fails validation.
    """
    agent, config = await agent_service.update_post_call_trigger(agent_id, auth, payload.model_dump(exclude_unset=True))
    return success_response(message="Post-call trigger configuration updated", data=agent_service.to_out(agent, config))
