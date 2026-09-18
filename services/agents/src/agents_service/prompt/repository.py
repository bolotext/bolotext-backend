from datetime import datetime, timezone

from beanie import PydanticObjectId

from agents_service.prompt.version_model import SystemPromptVersion


async def count_versions(agent_id: PydanticObjectId) -> int:
    return await SystemPromptVersion.find(SystemPromptVersion.agent_id == agent_id).count()


async def create_version(
    agent_id: PydanticObjectId, prompt_key: str, prompt_description: str | None, system_prompt: str, created_by: str
) -> SystemPromptVersion:
    version = SystemPromptVersion(
        agent_id=agent_id,
        prompt_key=prompt_key,
        prompt_description=prompt_description,
        system_prompt=system_prompt,
        created_by=created_by,
    )
    await version.insert()
    return version


async def list_versions(agent_id: PydanticObjectId) -> list[SystemPromptVersion]:
    return (
        await SystemPromptVersion.find(SystemPromptVersion.agent_id == agent_id)
        .sort(-SystemPromptVersion.created_at)
        .to_list()
    )


async def get_version(agent_id: PydanticObjectId, prompt_key: str) -> SystemPromptVersion | None:
    return await SystemPromptVersion.find_one(
        SystemPromptVersion.agent_id == agent_id, SystemPromptVersion.prompt_key == prompt_key
    )


async def save(version: SystemPromptVersion) -> SystemPromptVersion:
    version.updated_at = datetime.now(timezone.utc)
    await version.save()
    return version


async def delete_version(agent_id: PydanticObjectId, prompt_key: str) -> bool:
    result = await SystemPromptVersion.find_one(
        SystemPromptVersion.agent_id == agent_id, SystemPromptVersion.prompt_key == prompt_key
    )
    if result is None:
        return False
    await result.delete()
    return True


async def delete_all_versions(agent_id: PydanticObjectId) -> None:
    """Every version row for one agent — called when the agent itself is
    deleted (see agents.service.delete_agent), unlike delete_version above
    which only ever removes one specific version.
    """
    await SystemPromptVersion.find(SystemPromptVersion.agent_id == agent_id).delete()
