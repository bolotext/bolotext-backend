from beanie import PydanticObjectId

from agents_service.prompt.version_model import SystemPromptVersion


async def count_versions(agent_id: PydanticObjectId) -> int:
    return await SystemPromptVersion.find(SystemPromptVersion.agent_id == agent_id).count()


async def _latest_version_number(agent_id: PydanticObjectId) -> int:
    latest = (
        await SystemPromptVersion.find(SystemPromptVersion.agent_id == agent_id)
        .sort(-SystemPromptVersion.version)
        .first_or_none()
    )
    return latest.version if latest else 0


async def create_version(agent_id: PydanticObjectId, system_prompt: str, created_by: str) -> SystemPromptVersion:
    version_number = await _latest_version_number(agent_id) + 1
    version = SystemPromptVersion(
        agent_id=agent_id, version=version_number, system_prompt=system_prompt, created_by=created_by
    )
    await version.insert()
    return version


async def list_versions(agent_id: PydanticObjectId) -> list[SystemPromptVersion]:
    return (
        await SystemPromptVersion.find(SystemPromptVersion.agent_id == agent_id)
        .sort(-SystemPromptVersion.version)
        .to_list()
    )


async def get_version(agent_id: PydanticObjectId, version: int) -> SystemPromptVersion | None:
    return await SystemPromptVersion.find_one(
        SystemPromptVersion.agent_id == agent_id, SystemPromptVersion.version == version
    )


async def delete_version(agent_id: PydanticObjectId, version: int) -> bool:
    result = await SystemPromptVersion.find_one(
        SystemPromptVersion.agent_id == agent_id, SystemPromptVersion.version == version
    )
    if result is None:
        return False
    await result.delete()
    return True
