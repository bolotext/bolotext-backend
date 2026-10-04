from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from agents_service.agents import service as agent_service
from agents_service.agents.schema import AgentOut
from agents_service.core.deps import AuthContext, get_current_auth
from agents_service.llm.schema import LLMSettingsUpdate

router = APIRouter(prefix="/agents", tags=["agents:llm"])


@router.patch(
    "/{agent_id}/llm",
    response_model=SuccessResponse[AgentOut],
    summary="Update an agent's LLM settings",
)
async def update_llm(
    agent_id: PydanticObjectId, payload: LLMSettingsUpdate, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    """Partially updates the LLM provider/model, generation parameters, and
    linked knowledge bases for the agent's `development` environment. Only
    fields present in the request body are changed; omitted fields keep
    their current value. Returns the full, merged agent.

    **Auth:** bearer JWT required; caller must have access to this agent
    (own it, or be an Admin/QA in its organization — see `GET /agents/{id}`).

    **Errors:**
    - `NOT_FOUND` — no agent with this ID exists for the caller.
    - `FORBIDDEN` — caller isn't authorized to write to this agent (e.g. a
      Developer without this agent assigned to them).
    - `UNPROCESSABLE_ENTITY` — the payload fails validation against the LLM
      settings schema.
    """
    agent, config = await agent_service.update_section(agent_id, auth, "llm", payload.model_dump(exclude_unset=True))
    return success_response(message="Agent LLM settings updated", data=agent_service.to_out(agent, config))
