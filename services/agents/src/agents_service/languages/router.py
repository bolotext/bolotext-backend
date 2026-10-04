from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends, Path

from agents_service.agents import service as agent_service
from agents_service.agents.schema import AgentOut
from agents_service.core.deps import AuthContext, get_current_auth
from agents_service.languages.schema import LanguagesUpdate

router = APIRouter(prefix="/agents", tags=["agents:languages"])


@router.put(
    "/{agent_id}/languages",
    response_model=SuccessResponse[AgentOut],
    summary="Set an agent's languages",
)
async def update_languages(
    agent_id: PydanticObjectId = Path(description="The agent's id."),
    payload: LanguagesUpdate = ...,
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    """Replaces the full list of languages the agent's `development`
    environment supports. This is a full replace, not a merge — send every
    language the agent should support, not just the ones you're adding.

    **Auth:** bearer JWT required; caller must own the agent.

    **Errors:** `NOT_FOUND` if no such agent exists, or it belongs to
    another caller; `UNPROCESSABLE_ENTITY` if `languages` is empty.
    """
    agent, config = await agent_service.update_languages(agent_id, auth, payload.languages)
    return success_response(message="Agent languages updated", data=agent_service.to_out(agent, config))
