from datetime import datetime, timezone

from beanie import PydanticObjectId

from agents_service.agent_configs.model import AgentConfig


async def create_config(agent_id: PydanticObjectId) -> AgentConfig:
    config = AgentConfig(agent_id=agent_id)
    await config.insert()
    return config


async def get_by_agent_id(agent_id: PydanticObjectId) -> AgentConfig | None:
    return await AgentConfig.find_one(AgentConfig.agent_id == agent_id)


async def save(config: AgentConfig) -> AgentConfig:
    config.updated_at = datetime.now(timezone.utc)
    await config.save()
    return config
