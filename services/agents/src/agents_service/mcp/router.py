from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from agents_service.agents import service as agent_service
from agents_service.agents.schema import AgentOut
from agents_service.core.deps import AuthContext, get_current_auth
from agents_service.mcp.schema import MCPSettingsUpdate

router = APIRouter(prefix="/agents", tags=["agents:mcp"])


@router.patch(
    "/{agent_id}/mcp",
    response_model=SuccessResponse[AgentOut],
    summary="Update an agent's MCP server integrations",
)
async def update_mcp(
    agent_id: PydanticObjectId, payload: MCPSettingsUpdate, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    """Updates the agent's `development` environment with the Model Context
    Protocol (MCP) servers supplied in the payload — external MCP servers
    whose tools/resources the agent can use mid-call, alongside (or instead
    of) the simpler webhook-style tools configured via
    `PATCH /agents/{agent_id}/actions`. Only fields present in the payload
    are changed; `servers` is replaced wholesale when supplied.

    **Auth:** Bearer JWT required; the caller must own the agent.

    **Errors:**
    - `NOT_FOUND` — no agent with this ID exists for the caller.
    - `UNAUTHORIZED` — missing or invalid bearer token.
    - `UNPROCESSABLE_ENTITY` — the merged section fails validation.
    """
    agent, config = await agent_service.update_section(agent_id, auth, "mcp", payload.model_dump(exclude_unset=True))
    return success_response(message="Agent MCP servers updated", data=agent_service.to_out(agent, config))
