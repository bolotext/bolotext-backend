from datetime import datetime, timezone

from beanie import PydanticObjectId
from beanie.operators import In

from agents_service.agents.model import Agent, AgentStatus


async def create_agent(user_id: str, org_id: str | None, name: str, description: str | None) -> Agent:
    agent = Agent(user_id=user_id, org_id=org_id, name=name, description=description)
    await agent.insert()
    return agent


async def get_by_id(agent_id: PydanticObjectId) -> Agent | None:
    return await Agent.get(agent_id)


async def list_agents(
    user_id: str, skip: int = 0, limit: int = 50, status: AgentStatus | None = None
) -> list[Agent]:
    conditions = [Agent.user_id == user_id]
    if status is not None:
        conditions.append(Agent.status == status)
    return await Agent.find(*conditions).skip(skip).limit(limit).to_list()


async def list_by_org(
    org_id: str | None, skip: int = 0, limit: int = 50, status: AgentStatus | None = None
) -> list[Agent]:
    conditions = [Agent.org_id == org_id]
    if status is not None:
        conditions.append(Agent.status == status)
    return await Agent.find(*conditions).skip(skip).limit(limit).to_list()


async def list_by_ids(
    agent_ids: list[PydanticObjectId], skip: int = 0, limit: int = 50, status: AgentStatus | None = None
) -> list[Agent]:
    if not agent_ids:
        return []
    conditions = [In(Agent.id, agent_ids)]
    if status is not None:
        conditions.append(Agent.status == status)
    return await Agent.find(*conditions).skip(skip).limit(limit).to_list()


async def save(agent: Agent) -> Agent:
    agent.updated_at = datetime.now(timezone.utc)
    await agent.save()
    return agent


async def delete(agent: Agent) -> None:
    """Hard delete — see agents.service.delete_agent for the full cascade
    (AgentConfig rows across every environment, SystemPromptVersion rows);
    this only removes the Agent identity document itself.
    """
    await agent.delete()
