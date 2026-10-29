from typing import Literal

from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends, Path, Query

from agents_service.agent_configs.model import Environment
from agents_service.agent_details.schema import AgentDetails
from agents_service.agents import service as agent_service
from agents_service.agents.model import AgentStatus
from agents_service.agents.schema import AgentListItem, AgentOut, AgentStatusUpdate, EnvironmentSummary
from agents_service.core.deps import AuthContext, ServiceAuth, get_config_auth, get_current_auth

router = APIRouter(prefix="/agents", tags=["agents"])
# Separate router so app.py can leave off the `?env=` write-environment dependency:
# GET /agents/config takes its own `environment` param. Included before `router`
# so "config" isn't parsed as an `/{agent_id}`.
agent_config_router = APIRouter(prefix="/agents", tags=["agents"])

_AGENT_ID_PATH = Path(description="The agent's id.")


@router.post("", response_model=SuccessResponse[AgentOut], summary="Create a new agent")
async def create_agent(payload: AgentDetails, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Creates a new agent owned by the caller, seeded with default settings
    for every builder tab (prompt, flow, transcriber, llm, voice persona,
    etc.) and a single `development` environment — English-only
    (`languages: ["en-IN"]`) until configured via `PUT /agents/{id}/languages`.

    **Auth:** bearer JWT required; the created agent is owned by the caller.

    **Errors:** `UNPROCESSABLE_ENTITY` if `agent_details` fails a save-time
    business rule.
    """
    agent, config = await agent_service.create_agent(auth, payload)
    return success_response(code=201, message="Agent created", data=agent_service.to_out(agent, config))


@router.get("", response_model=SuccessResponse[list[AgentListItem]], summary="List agents")
async def list_agents(
    skip: int = Query(0, ge=0, description="Number of agents to skip, for pagination."),
    limit: int = Query(10, ge=1, description="Maximum number of agents to return."),
    status: AgentStatus | None = Query(
        None, description='Filter by agent status: "active" or "inactive". Omit to return agents in any status.'
    ),
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    """Lists the caller's agents (identity fields only — no builder-tab
    sections; fetch `GET /agents/{agent_id}` for the full merged view of a
    single agent), newest first, optionally filtered by status.

    **Auth:** bearer JWT required; only the caller's own agents are returned.
    """
    agents = await agent_service.list_agents(auth, skip=skip, limit=limit, status=status)
    return success_response(data=[agent_service.to_list_item(agent) for agent in agents])


@agent_config_router.get(
    "/config",
    response_model=SuccessResponse[AgentOut],
    summary="Get an agent's config for an environment (query params)",
)
async def get_agent_config(
    agent_id: PydanticObjectId = Query(description="The agent's id."),
    environment: Literal["development", "stage", "production"] = Query(
        description='Which environment to read: "development", "stage" or "production".'
    ),
    auth: AuthContext | ServiceAuth = Depends(get_config_auth),
) -> dict:
    """Returns the agent's full config (identity plus every builder-tab
    section) as it exists in the requested environment. Same payload as
    `GET /agents/{agent_id}/environments/{environment}`, addressed by query
    parameters instead of path segments.

    **Auth:** bearer token required — either a user JWT (the caller must own
    the agent) or a Super-Admin-issued, non-expiring API token with the
    `agent-config:read` scope (create one via `POST /api-tokens`), which can
    read any agent's config. API tokens work only on this route.

    **Errors:** `NOT_FOUND` if no such agent exists, it belongs to another
    caller, or the environment has never been populated (`stage`/
    `production` before the first promotion). `UNPROCESSABLE_ENTITY` for a
    missing/invalid `agent_id` or an unknown `environment`.
    """
    env: Environment = environment
    if isinstance(auth, ServiceAuth):
        agent, config = await agent_service.get_agent_environment_for_service(agent_id, env)
    else:
        agent, config = await agent_service.get_agent_environment(agent_id, auth, env)
    return success_response(data=agent_service.to_out(agent, config))


@router.get("/{agent_id}", response_model=SuccessResponse[AgentOut], summary="Get an agent")
async def get_agent(agent_id: PydanticObjectId = _AGENT_ID_PATH, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Returns the full merged view of one agent (identity plus every
    builder-tab section) in its `development` environment.

    **Auth:** bearer JWT required; caller must own the agent.

    **Errors:** `NOT_FOUND` if no such agent exists, or it belongs to another
    caller.
    """
    agent, config = await agent_service.get_agent_with_config(agent_id, auth, write=False)
    return success_response(data=agent_service.to_out(agent, config))


@router.delete("/{agent_id}", response_model=SuccessResponse[AgentOut], summary="Delete an agent")
async def delete_agent(agent_id: PydanticObjectId = _AGENT_ID_PATH, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Permanently deletes an agent. This is a hard delete with no undo: it
    cascades to every environment's config (`development`/`stage`/
    `production`) and the agent's system-prompt version history.

    **Auth:** bearer JWT required; caller must own the agent.

    **Errors:** `NOT_FOUND` if no such agent exists, or it belongs to another
    caller.
    """
    # Hard delete, cascading to every environment's config and system-prompt
    # version history — see agents.service.delete_agent.
    agent, config = await agent_service.delete_agent(agent_id, auth)
    return success_response(message="Agent and all related data deleted", data=agent_service.to_out(agent, config))


@router.patch("/{agent_id}/status", response_model=SuccessResponse[AgentOut], summary="Set an agent's status")
async def update_agent_status(
    agent_id: PydanticObjectId = _AGENT_ID_PATH,
    payload: AgentStatusUpdate = ...,
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    """Sets an agent's status directly to `active` or `inactive`. Equivalent
    to `POST .../activate` or `POST .../deactivate`, provided as a single
    generic route.

    **Auth:** bearer JWT required; caller must own the agent.

    **Errors:** `NOT_FOUND` if no such agent exists, or it belongs to another
    caller.
    """
    agent, config = await agent_service.update_status(agent_id, auth, payload.status)
    return success_response(message="Agent status updated", data=agent_service.to_out(agent, config))


@router.post("/{agent_id}/activate", response_model=SuccessResponse[AgentOut], summary="Activate an agent")
async def activate_agent(agent_id: PydanticObjectId = _AGENT_ID_PATH, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Sets an agent's status to `active`. Shortcut for
    `PATCH .../status {"status": "active"}`.

    **Auth:** bearer JWT required; caller must own the agent.

    **Errors:** `NOT_FOUND` if no such agent exists, or it belongs to another
    caller.
    """
    agent, config = await agent_service.activate_agent(agent_id, auth)
    return success_response(message="Agent activated", data=agent_service.to_out(agent, config))


@router.post("/{agent_id}/deactivate", response_model=SuccessResponse[AgentOut], summary="Deactivate an agent")
async def deactivate_agent(agent_id: PydanticObjectId = _AGENT_ID_PATH, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Sets an agent's status to `inactive`. Shortcut for
    `PATCH .../status {"status": "inactive"}`.

    **Auth:** bearer JWT required; caller must own the agent.

    **Errors:** `NOT_FOUND` if no such agent exists, or it belongs to another
    caller.
    """
    agent, config = await agent_service.deactivate_agent(agent_id, auth)
    return success_response(message="Agent deactivated", data=agent_service.to_out(agent, config))


@router.post("/{agent_id}/clone", response_model=SuccessResponse[AgentOut], summary="Clone an agent")
async def clone_agent(agent_id: PydanticObjectId = _AGENT_ID_PATH, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Creates a new agent by copying this agent's `development`
    environment (identity and every builder-tab section). The clone is
    independent afterwards — editing one never affects the other.

    **Auth:** bearer JWT required; caller must own the source agent. The
    clone is owned by the caller.

    **Errors:** `NOT_FOUND` if no such agent exists, or it belongs to another
    caller.
    """
    agent, config = await agent_service.clone_agent(agent_id, auth)
    return success_response(code=201, message="Agent cloned", data=agent_service.to_out(agent, config))


# --- environments (development/stage/production) -----------------------------
# `development` is edited directly through every tab's own PATCH route (it's
# the implicit environment those already target). `stage` and `production`
# are read-only snapshots, only ever written by the promotion routes below.


@router.get(
    "/{agent_id}/environments",
    response_model=SuccessResponse[list[EnvironmentSummary]],
    summary="List an agent's environments",
)
async def list_agent_environments(
    agent_id: PydanticObjectId = _AGENT_ID_PATH, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    """Returns a summary row for each of the agent's three environments
    (`development`, `stage`, `production`) — whether it exists yet
    (`stage`/`production` don't until first promoted) and when it was last
    updated — without fetching each one's full config.

    **Auth:** bearer JWT required; caller must own the agent.

    **Errors:** `NOT_FOUND` if no such agent exists, or it belongs to another
    caller.
    """
    summaries = await agent_service.list_environment_summaries(agent_id, auth)
    return success_response(data=summaries)


@router.get(
    "/{agent_id}/environments/{environment}",
    response_model=SuccessResponse[AgentOut],
    summary="Get an agent in a specific environment",
)
async def get_agent_environment(
    agent_id: PydanticObjectId = _AGENT_ID_PATH,
    environment: Environment = Path(
        description='Which environment snapshot to read: "development" (live, directly editable), '
        '"stage", or "production" (both read-only, written only by promotion).'
    ),
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    """Returns the full merged view of the agent as it exists in the given
    environment. Use this to read the `stage`/`production` snapshot, since
    `GET /agents/{agent_id}` always returns `development`.

    **Auth:** bearer JWT required; caller must own the agent.

    **Errors:** `NOT_FOUND` if no such agent exists, it belongs to another
    caller, or the requested environment has never been populated (e.g.
    `stage` before the first promotion).
    """
    agent, config = await agent_service.get_agent_environment(agent_id, auth, environment)
    return success_response(data=agent_service.to_out(agent, config))


@router.post(
    "/{agent_id}/move-to-stage", response_model=SuccessResponse[AgentOut], summary="Promote development to stage"
)
async def move_to_stage(agent_id: PydanticObjectId = _AGENT_ID_PATH, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Overwrites the agent's `stage` environment with a snapshot of its
    current `development` config. Use this to move in-progress edits into a
    pre-production environment for testing before `move-to-prod`.

    **Auth:** bearer JWT required; caller must own the agent.

    **Errors:** `NOT_FOUND` if no such agent exists, or it belongs to another
    caller.
    """
    agent, config = await agent_service.move_to_stage(agent_id, auth)
    return success_response(message="Development config promoted to stage", data=agent_service.to_out(agent, config))


@router.post(
    "/{agent_id}/move-to-prod", response_model=SuccessResponse[AgentOut], summary="Promote stage to production"
)
async def move_to_prod(agent_id: PydanticObjectId = _AGENT_ID_PATH, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Overwrites the agent's `production` environment with a snapshot of
    its current `stage` config. This is the route that makes an agent's
    latest tested changes live.

    **Auth:** bearer JWT required; caller must own the agent.

    **Errors:** `NOT_FOUND` if no such agent exists, it belongs to another
    caller, or `stage` hasn't been populated yet (nothing to promote).
    """
    agent, config = await agent_service.move_to_prod(agent_id, auth)
    return success_response(message="Stage config promoted to production", data=agent_service.to_out(agent, config))
