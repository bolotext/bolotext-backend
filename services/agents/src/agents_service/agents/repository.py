from datetime import datetime, timezone

from beanie import PydanticObjectId
from beanie.operators import Set

from agents_service.agents.model import Agent, AgentStatus


async def create_agent(user_id: str, org_id: str | None, name: str, description: str | None) -> Agent:
    agent = Agent(user_id=user_id, org_id=org_id, name=name, description=description)
    await agent.insert()
    return agent


async def get_by_id(agent_id: PydanticObjectId) -> Agent | None:
    agent = await Agent.get(agent_id)
    if agent is None or agent.deleted_at is not None:
        return None
    return agent


async def list_agents(
    user_id: str, skip: int = 0, limit: int = 50, status: AgentStatus | None = None
) -> list[Agent]:
    conditions = [Agent.user_id == user_id, Agent.deleted_at == None]  # noqa: E711 - Beanie operator requires `==`
    if status is not None:
        conditions.append(Agent.status == status)
    return await Agent.find(*conditions).skip(skip).limit(limit).to_list()


async def save(agent: Agent) -> Agent:
    agent.updated_at = datetime.now(timezone.utc)
    await agent.save()
    return agent


async def soft_delete(agent: Agent) -> Agent:
    now = datetime.now(timezone.utc)
    agent.deleted_at = now
    agent.updated_at = now
    await agent.update(Set({Agent.deleted_at: now, Agent.updated_at: now}))
    return agent
