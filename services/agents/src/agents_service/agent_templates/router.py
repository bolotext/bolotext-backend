from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends, Path

from agents_service.agent_templates import service as template_service
from agents_service.agent_templates.schema import (
    AgentFromTemplateRequest,
    AgentTemplateOut,
    AgentTemplateSummary,
)
from agents_service.agents import service as agent_service
from agents_service.agents.schema import AgentOut
from agents_service.core.deps import AuthContext, get_current_auth

router = APIRouter(prefix="/agent-templates", tags=["agent-templates"])

_KEY_PATH = Path(description="The template's key, e.g. `appointment-booking`.")


@router.get("", response_model=SuccessResponse[list[AgentTemplateSummary]], summary="List agent templates")
async def list_templates(auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Lists the built-in starter templates (appointment booking, insurance
    renewal, loan enquiry, EMI reminder, feedback survey).

    **Auth:** bearer JWT required.
    """
    return success_response(data=template_service.list_templates())


@router.get("/{key}", response_model=SuccessResponse[AgentTemplateOut], summary="Get an agent template")
async def get_template(key: str = _KEY_PATH, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Returns one template in full: prompt text, pre-call variables, FAQ,
    languages and the regulatory notes to review before production.

    **Auth:** bearer JWT required.

    **Errors:** `NOT_FOUND` if the key is unknown.
    """
    return success_response(data=template_service.get_template(key))


@router.post(
    "/{key}/create-agent",
    response_model=SuccessResponse[AgentOut],
    summary="Create an agent from a template",
)
async def create_agent_from_template(
    key: str = _KEY_PATH,
    payload: AgentFromTemplateRequest = AgentFromTemplateRequest(),
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    """Creates a new agent with the template's prompt, pre-call variables,
    FAQ and languages already filled in. The agent is an independent copy;
    edit it like any other agent. Templates are drafts — review them (and
    have Legal/Compliance sign off) before production use.

    **Auth:** bearer JWT required; QA cannot create agents.

    **Errors:** `NOT_FOUND` if the key is unknown; `FORBIDDEN` for QA callers.
    """
    agent, config = await template_service.create_agent_from_template(auth, key, payload)
    return success_response(code=201, message="Agent created from template", data=agent_service.to_out(agent, config))
