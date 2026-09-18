from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from agents_service.agents import service as agent_service
from agents_service.agents.schema import AgentOut
from agents_service.core.deps import AuthContext, get_current_auth
from agents_service.mcp.schema import MCPSettingsUpdate

router = APIRouter(prefix="/agents", tags=["agents:mcp"])


@router.patch("/{agent_id}/mcp", response_model=SuccessResponse[AgentOut])
async def update_mcp(
    agent_id: PydanticObjectId, payload: MCPSettingsUpdate, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    agent, config = await agent_service.update_section(agent_id, auth, "mcp", payload.model_dump(exclude_unset=True))
    return success_response(message="Agent MCP servers updated", data=agent_service.to_out(agent, config))
