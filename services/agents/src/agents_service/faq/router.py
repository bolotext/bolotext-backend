from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from agents_service.agents import service as agent_service
from agents_service.agents.schema import AgentOut
from agents_service.core.deps import AuthContext, get_current_auth
from agents_service.faq.schema import FAQSettingsUpdate

router = APIRouter(prefix="/agents", tags=["agents:faq"])


@router.patch(
    "/{agent_id}/faq",
    response_model=SuccessResponse[AgentOut],
    summary="Update an agent's FAQ answers",
)
async def update_faq(
    agent_id: PydanticObjectId, payload: FAQSettingsUpdate, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    """Updates the agent's `development` environment with the FAQ
    question/answer pairs supplied in the payload, which the agent can draw
    on to answer common caller questions. Only fields present in the
    payload are changed; omitted fields keep their current value. Note
    `pairs` is replaced wholesale when supplied — send the full desired list,
    not just the pairs you want to add.

    **Auth:** Bearer JWT required; the caller must own the agent.

    **Errors:**
    - `NOT_FOUND` — no agent with this ID exists for the caller.
    - `UNAUTHORIZED` — missing or invalid bearer token.
    - `UNPROCESSABLE_ENTITY` — the merged section fails validation.
    """
    agent, config = await agent_service.update_section(agent_id, auth, "faq", payload.model_dump(exclude_unset=True))
    return success_response(message="Agent FAQ answers updated", data=agent_service.to_out(agent, config))
