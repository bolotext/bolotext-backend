from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from agents_service.agents import service as agent_service
from agents_service.agents.schema import AgentOut
from agents_service.core.deps import AuthContext, get_current_auth
from agents_service.precall_variables.schema import PreCallVariablesUpdate

router = APIRouter(prefix="/agents", tags=["agents:precall-variables"])


@router.put(
    "/{agent_id}/pre-call-variables",
    response_model=SuccessResponse[AgentOut],
    summary="Replace an agent's pre-call variable defaults",
)
async def update_pre_call_variables(
    agent_id: PydanticObjectId, payload: PreCallVariablesUpdate, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    """Fully replaces the agent's pre-call variable defaults and whether
    they're applied (this is a PUT, not a PATCH: the two fields together are
    the whole of what this route owns, so "replace" and "set" are the same
    operation). These defaults resolve `{{variable}}` placeholders in the
    prompt whenever a call doesn't supply its own override. Returns the
    full, merged agent.

    **Auth:** bearer JWT required; caller must have access to this agent
    (own it, or be an Admin/QA in its organization — see `GET /agents/{id}`).

    **Errors:**
    - `NOT_FOUND` — no agent with this ID exists for the caller.
    - `FORBIDDEN` — caller isn't authorized to write to this agent (e.g. a
      Developer without this agent assigned to them).
    - `UNPROCESSABLE_ENTITY` — the payload fails validation.
    """
    agent, config = await agent_service.update_pre_call_variables(
        agent_id, auth, payload.pre_call_variables, payload.pre_call_variables_enabled
    )
    return success_response(message="Pre-call variables updated", data=agent_service.to_out(agent, config))
