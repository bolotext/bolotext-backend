from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from agents_service.actions.schema import ActionsSettingsUpdate
from agents_service.agents import service as agent_service
from agents_service.agents.schema import AgentOut
from agents_service.core.deps import AuthContext, get_current_auth

router = APIRouter(prefix="/agents", tags=["agents:actions"])


@router.patch(
    "/{agent_id}/actions",
    response_model=SuccessResponse[AgentOut],
    summary="Update an agent's custom actions",
)
async def update_actions(
    agent_id: PydanticObjectId, payload: ActionsSettingsUpdate, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    """Updates the agent's `development` environment with the custom
    actions supplied in the payload — HTTP callouts (functions/tools) the
    agent can invoke mid-call, e.g. to reserve a slot or look up an account.
    Only fields present in the payload are changed; omitted fields keep
    their current value. Promote via `/agents/{agent_id}/move-to-stage` and
    `/move-to-prod` to carry the change beyond `development`.

    **Auth:** Bearer JWT required; the caller must own the agent.

    **Errors:**
    - `NOT_FOUND` — no agent with this ID exists for the caller.
    - `UNAUTHORIZED` — missing or invalid bearer token.
    - `UNPROCESSABLE_ENTITY` — the merged section fails validation.
    """
    agent, config = await agent_service.update_section(agent_id, auth, "actions", payload.model_dump(exclude_unset=True))
    return success_response(message="Agent actions updated", data=agent_service.to_out(agent, config))
