from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from agents_service.agents import service as agent_service
from agents_service.agents.schema import AgentOut
from agents_service.core.deps import AuthContext, get_current_auth
from agents_service.others.schema import OthersSettingsUpdate

router = APIRouter(prefix="/agents", tags=["agents:others"])


@router.patch(
    "/{agent_id}/others",
    response_model=SuccessResponse[AgentOut],
    summary="Update an agent's miscellaneous settings",
)
async def update_others(
    agent_id: PydanticObjectId, payload: OthersSettingsUpdate, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    """Updates the agent's `development` environment with the miscellaneous
    settings supplied in the payload — currently voicemail detection and
    call transfer behavior. Only fields present in the payload are changed;
    omitted fields keep their current value.

    **Auth:** Bearer JWT required; the caller must own the agent.

    **Errors:**
    - `NOT_FOUND` — no agent with this ID exists for the caller.
    - `UNAUTHORIZED` — missing or invalid bearer token.
    - `UNPROCESSABLE_ENTITY` — the merged section fails validation.
    """
    agent, config = await agent_service.update_section(agent_id, auth, "others", payload.model_dump(exclude_unset=True))
    return success_response(message="Agent settings updated", data=agent_service.to_out(agent, config))
