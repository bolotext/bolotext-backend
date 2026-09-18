from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from agents_service.agents import service as agent_service
from agents_service.agents.schema import AgentOut
from agents_service.core.deps import AuthContext, get_current_auth
from agents_service.prompt import service as prompt_service
from agents_service.prompt.schema import (
    LanguageSwitchPreviewResponse,
    LanguageSwitchSettingsUpdate,
    PromptMessagesUpdate,
    SystemPromptReplace,
    SystemPromptVersionCreate,
    SystemPromptVersionOut,
    TestRenderRequest,
    TestRenderResponse,
)
from agents_service.prompt.version_model import SystemPromptVersion

router = APIRouter(prefix="/agents", tags=["agents:prompt"])


def _version_out(version: SystemPromptVersion) -> SystemPromptVersionOut:
    return SystemPromptVersionOut(
        prompt_key=version.prompt_key,
        prompt_description=version.prompt_description,
        system_prompt=version.system_prompt,
        created_by=version.created_by,
        created_at=version.created_at,
        updated_at=version.updated_at,
    )


@router.patch("/{agent_id}/prompt/messages", response_model=SuccessResponse[AgentOut])
async def update_prompt_messages(
    agent_id: PydanticObjectId, payload: PromptMessagesUpdate, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    agent, config = await agent_service.update_prompt_messages(agent_id, auth, payload.model_dump(exclude_unset=True))
    return success_response(message="Agent prompt messages updated", data=agent_service.to_out(agent, config))


@router.patch("/{agent_id}/prompt/language-switch", response_model=SuccessResponse[AgentOut])
async def update_language_switch_settings(
    agent_id: PydanticObjectId, payload: LanguageSwitchSettingsUpdate, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    agent, config = await agent_service.update_language_switch_settings(
        agent_id, auth, payload.model_dump(exclude_unset=True)
    )
    return success_response(message="Agent language switch settings updated", data=agent_service.to_out(agent, config))


@router.post("/{agent_id}/test", response_model=SuccessResponse[TestRenderResponse])
async def test_agent_prompt(
    agent_id: PydanticObjectId,
    payload: TestRenderRequest = TestRenderRequest(),
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    rendered = await agent_service.render_test(agent_id, auth, payload.sample_values)
    return success_response(data=TestRenderResponse(**rendered))


@router.get("/{agent_id}/prompt/language-switch-preview", response_model=SuccessResponse[LanguageSwitchPreviewResponse])
async def preview_language_switch_prompt(
    agent_id: PydanticObjectId, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    mode, languages, prompt = await agent_service.preview_language_switch_prompt(agent_id, auth)
    return success_response(data=LanguageSwitchPreviewResponse(mode=mode, languages=languages, prompt=prompt))


# --- system prompt versions (create/list/replace/delete; see prompt/version_model.py) ---


@router.post("/{agent_id}/prompt/versions", response_model=SuccessResponse[SystemPromptVersionOut])
async def create_system_prompt_version(
    agent_id: PydanticObjectId, payload: SystemPromptVersionCreate, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    await agent_service.get_owned_agent(agent_id, auth)
    version = await prompt_service.create_system_prompt_version(agent_id, payload, auth.user_id)
    return success_response(code=201, message="System prompt version created", data=_version_out(version))


@router.get("/{agent_id}/prompt/versions", response_model=SuccessResponse[list[SystemPromptVersionOut]])
async def list_system_prompt_versions(
    agent_id: PydanticObjectId, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    # Ownership check only — the versions themselves live in their own
    # collection (system_prompt_versions), not on AgentConfig.
    await agent_service.get_owned_agent(agent_id, auth, write=False)
    versions = await prompt_service.list_system_prompt_versions(agent_id)
    return success_response(data=[_version_out(v) for v in versions])


@router.patch("/{agent_id}/prompt/versions", response_model=SuccessResponse[SystemPromptVersionOut])
async def replace_system_prompt(
    agent_id: PydanticObjectId, payload: SystemPromptReplace, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    await agent_service.get_owned_agent(agent_id, auth)
    version = await prompt_service.replace_system_prompt(agent_id, payload)
    return success_response(message="System prompt replaced", data=_version_out(version))


@router.delete("/{agent_id}/prompt/versions/{prompt_key}", response_model=SuccessResponse[None])
async def delete_system_prompt_version(
    agent_id: PydanticObjectId, prompt_key: str, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    # Ownership check only, same as the other version routes — a version is
    # just a saved library entry now, nothing on AgentConfig ever points at
    # one, so there's nothing else to check before deleting it.
    await agent_service.get_owned_agent(agent_id, auth)
    await prompt_service.delete_system_prompt_version(agent_id, prompt_key)
    return success_response(message="System prompt version deleted")
