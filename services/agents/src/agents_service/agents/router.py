from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from agents_service.agent_details.schema import AgentDetails
from agents_service.agents import service as agent_service
from agents_service.agents.model import AgentStatus
from agents_service.agents.schema import AgentOut, AgentReplace
from agents_service.core.deps import AuthContext, get_current_auth

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("", response_model=SuccessResponse[AgentOut])
async def create_agent(payload: AgentDetails, auth: AuthContext = Depends(get_current_auth)) -> dict:
    agent, config = await agent_service.create_agent(auth, payload)
    return success_response(code=201, message="Agent created", data=agent_service.to_out(agent, config))


@router.get("", response_model=SuccessResponse[list[AgentOut]])
async def list_agents(
    skip: int = 0,
    limit: int = 50,
    status: AgentStatus | None = None,
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    pairs = await agent_service.list_agents(auth, skip=skip, limit=limit, status=status)
    return success_response(data=[agent_service.to_out(agent, config) for agent, config in pairs])


@router.get("/{agent_id}", response_model=SuccessResponse[AgentOut])
async def get_agent(agent_id: PydanticObjectId, auth: AuthContext = Depends(get_current_auth)) -> dict:
    agent, config = await agent_service.get_agent_with_config(agent_id, auth)
    return success_response(data=agent_service.to_out(agent, config))


@router.put("/{agent_id}", response_model=SuccessResponse[AgentOut])
async def replace_agent(
    agent_id: PydanticObjectId, payload: AgentReplace, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    agent, config = await agent_service.replace_agent(agent_id, auth, payload)
    return success_response(message="Agent replaced", data=agent_service.to_out(agent, config))


@router.delete("/{agent_id}", response_model=SuccessResponse[AgentOut])
async def delete_agent(agent_id: PydanticObjectId, auth: AuthContext = Depends(get_current_auth)) -> dict:
    agent, config = await agent_service.soft_delete_agent(agent_id, auth)
    return success_response(message="Agent deleted", data=agent_service.to_out(agent, config))


@router.post("/{agent_id}/publish", response_model=SuccessResponse[AgentOut])
async def publish_agent(agent_id: PydanticObjectId, auth: AuthContext = Depends(get_current_auth)) -> dict:
    agent, config = await agent_service.publish_agent(agent_id, auth)
    return success_response(message="Agent published", data=agent_service.to_out(agent, config))


@router.post("/{agent_id}/clone", response_model=SuccessResponse[AgentOut])
async def clone_agent(agent_id: PydanticObjectId, auth: AuthContext = Depends(get_current_auth)) -> dict:
    agent, config = await agent_service.clone_agent(agent_id, auth)
    return success_response(code=201, message="Agent cloned", data=agent_service.to_out(agent, config))
