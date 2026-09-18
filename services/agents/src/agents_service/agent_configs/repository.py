from datetime import datetime, timezone

from beanie import PydanticObjectId

from agents_service.agent_configs.model import AgentConfig, Environment


async def create_config(agent_id: PydanticObjectId, environment: Environment = "development") -> AgentConfig:
    config = AgentConfig(agent_id=agent_id, environment=environment)
    await config.insert()
    return config


async def get_by_agent_id(agent_id: PydanticObjectId, environment: Environment = "development") -> AgentConfig | None:
    return await AgentConfig.find_one(AgentConfig.agent_id == agent_id, AgentConfig.environment == environment)


async def list_by_agent_id(agent_id: PydanticObjectId) -> list[AgentConfig]:
    """Every environment's config for one agent — used to summarize which
    environments exist yet (agents/router.list_agent_environments).
    """
    return await AgentConfig.find(AgentConfig.agent_id == agent_id).to_list()


async def save(config: AgentConfig) -> AgentConfig:
    config.updated_at = datetime.now(timezone.utc)
    await config.save()
    return config


async def delete_all_by_agent_id(agent_id: PydanticObjectId) -> None:
    """Every environment's config for one agent — called when the agent
    itself is deleted (see agents.service.delete_agent) so no AgentConfig
    row (development/stage/production) is left orphaned.
    """
    await AgentConfig.find(AgentConfig.agent_id == agent_id).delete()
