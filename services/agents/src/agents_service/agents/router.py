from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from agents_service.agent_configs.model import Environment
from agents_service.agent_details.schema import AgentDetails
from agents_service.agents import service as agent_service
from agents_service.agents.model import AgentStatus
from agents_service.agents.schema import AgentListItem, AgentOut, AgentStatusUpdate, EnvironmentSummary
from agents_service.core.deps import AuthContext, get_current_auth

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("", response_model=SuccessResponse[AgentOut])
async def create_agent(payload: AgentDetails, auth: AuthContext = Depends(get_current_auth)) -> dict:
    agent, config = await agent_service.create_agent(auth, payload)
    return success_response(code=201, message="Agent created", data=agent_service.to_out(agent, config))


@router.get("", response_model=SuccessResponse[list[AgentListItem]])
async def list_agents(
    skip: int = 0,
    limit: int = 10,
    status: AgentStatus | None = None,
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    agents = await agent_service.list_agents(auth, skip=skip, limit=limit, status=status)
    return success_response(data=[agent_service.to_list_item(agent) for agent in agents])


@router.get("/{agent_id}", response_model=SuccessResponse[AgentOut])
async def get_agent(agent_id: PydanticObjectId, auth: AuthContext = Depends(get_current_auth)) -> dict:
    agent, config = await agent_service.get_agent_with_config(agent_id, auth, write=False)
    return success_response(data=agent_service.to_out(agent, config))


@router.delete("/{agent_id}", response_model=SuccessResponse[AgentOut])
async def delete_agent(agent_id: PydanticObjectId, auth: AuthContext = Depends(get_current_auth)) -> dict:
    # Hard delete, cascading to every environment's config and system-prompt
    # version history — see agents.service.delete_agent.
    agent, config = await agent_service.delete_agent(agent_id, auth)
    return success_response(message="Agent and all related data deleted", data=agent_service.to_out(agent, config))


@router.patch("/{agent_id}/status", response_model=SuccessResponse[AgentOut])
async def update_agent_status(
    agent_id: PydanticObjectId, payload: AgentStatusUpdate, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    agent, config = await agent_service.update_status(agent_id, auth, payload.status)
    return success_response(message="Agent status updated", data=agent_service.to_out(agent, config))


@router.post("/{agent_id}/activate", response_model=SuccessResponse[AgentOut])
async def activate_agent(agent_id: PydanticObjectId, auth: AuthContext = Depends(get_current_auth)) -> dict:
    agent, config = await agent_service.activate_agent(agent_id, auth)
    return success_response(message="Agent activated", data=agent_service.to_out(agent, config))


@router.post("/{agent_id}/deactivate", response_model=SuccessResponse[AgentOut])
async def deactivate_agent(agent_id: PydanticObjectId, auth: AuthContext = Depends(get_current_auth)) -> dict:
    agent, config = await agent_service.deactivate_agent(agent_id, auth)
    return success_response(message="Agent deactivated", data=agent_service.to_out(agent, config))


@router.post("/{agent_id}/clone", response_model=SuccessResponse[AgentOut])
async def clone_agent(agent_id: PydanticObjectId, auth: AuthContext = Depends(get_current_auth)) -> dict:
    agent, config = await agent_service.clone_agent(agent_id, auth)
    return success_response(code=201, message="Agent cloned", data=agent_service.to_out(agent, config))


# --- environments (development/stage/production) -----------------------------
# `development` is edited directly through every tab's own PATCH route (it's
# the implicit environment those already target). `stage` and `production`
# are read-only snapshots, only ever written by the promotion routes below.


@router.get("/{agent_id}/environments", response_model=SuccessResponse[list[EnvironmentSummary]])
async def list_agent_environments(agent_id: PydanticObjectId, auth: AuthContext = Depends(get_current_auth)) -> dict:
    summaries = await agent_service.list_environment_summaries(agent_id, auth)
    return success_response(data=summaries)


@router.get("/{agent_id}/environments/{environment}", response_model=SuccessResponse[AgentOut])
async def get_agent_environment(
    agent_id: PydanticObjectId, environment: Environment, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    agent, config = await agent_service.get_agent_environment(agent_id, auth, environment)
    return success_response(data=agent_service.to_out(agent, config))


@router.post("/{agent_id}/move-to-stage", response_model=SuccessResponse[AgentOut])
async def move_to_stage(agent_id: PydanticObjectId, auth: AuthContext = Depends(get_current_auth)) -> dict:
    agent, config = await agent_service.move_to_stage(agent_id, auth)
    return success_response(message="Development config promoted to stage", data=agent_service.to_out(agent, config))


@router.post("/{agent_id}/move-to-prod", response_model=SuccessResponse[AgentOut])
async def move_to_prod(agent_id: PydanticObjectId, auth: AuthContext = Depends(get_current_auth)) -> dict:
    agent, config = await agent_service.move_to_prod(agent_id, auth)
    return success_response(message="Stage config promoted to production", data=agent_service.to_out(agent, config))
