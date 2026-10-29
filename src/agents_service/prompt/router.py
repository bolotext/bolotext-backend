from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends, Path

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

_AGENT_ID_PATH = Path(description="The agent's id.")


def _version_out(version: SystemPromptVersion) -> SystemPromptVersionOut:
    return SystemPromptVersionOut(
        prompt_key=version.prompt_key,
        prompt_description=version.prompt_description,
        system_prompt=version.system_prompt,
        created_by=version.created_by,
        created_at=version.created_at,
        updated_at=version.updated_at,
    )


@router.patch(
    "/{agent_id}/prompt/messages",
    response_model=SuccessResponse[AgentOut],
    summary="Update an agent's prompt messages",
)
async def update_prompt_messages(
    agent_id: PydanticObjectId = _AGENT_ID_PATH,
    payload: PromptMessagesUpdate = ...,
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    """Partially updates the welcome/system/ending message text on the
    agent's `development` environment. Only the fields supplied are changed.
    `{{variable}}` placeholders in this text are resolved at call time (or by
    `POST /agents/{agent_id}/test`) from `prompt.pre_call_variables` and any
    values supplied by the caller — see
    `PUT /agents/{agent_id}/pre-call-variables`.

    **Auth:** bearer JWT required; caller must own the agent.

    **Errors:** `NOT_FOUND` if no such agent exists, or it belongs to
    another caller; `UNPROCESSABLE_ENTITY` if a `{{variable}}` reference
    isn't a declared pre-call variable.
    """
    agent, config = await agent_service.update_prompt_messages(agent_id, auth, payload.model_dump(exclude_unset=True))
    return success_response(message="Agent prompt messages updated", data=agent_service.to_out(agent, config))


@router.patch(
    "/{agent_id}/prompt/language-switch",
    response_model=SuccessResponse[AgentOut],
    summary="Update an agent's language-switch settings",
)
async def update_language_switch_settings(
    agent_id: PydanticObjectId = _AGENT_ID_PATH,
    payload: LanguageSwitchSettingsUpdate = ...,
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    """Partially updates how the agent detects and switches between its
    configured languages mid-call (`implicit`/`explicit` built-in behavior,
    or a fully `custom` prompt). Only the fields supplied are changed. Use
    `GET .../prompt/language-switch-preview` to see the resulting prompt.

    **Auth:** bearer JWT required; caller must own the agent.

    **Errors:** `NOT_FOUND` if no such agent exists, or it belongs to
    another caller; `UNPROCESSABLE_ENTITY` if `language_switch_mode` is set
    to `"custom"` without a `language_switch_prompt`.
    """
    agent, config = await agent_service.update_language_switch_settings(
        agent_id, auth, payload.model_dump(exclude_unset=True)
    )
    return success_response(message="Agent language switch settings updated", data=agent_service.to_out(agent, config))


@router.post(
    "/{agent_id}/test",
    response_model=SuccessResponse[TestRenderResponse],
    summary="Preview a rendered prompt",
)
async def test_agent_prompt(
    agent_id: PydanticObjectId = _AGENT_ID_PATH,
    payload: TestRenderRequest = TestRenderRequest(),
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    """Renders the agent's welcome/system/ending messages with
    `{{variable}}` placeholders resolved, without starting a real call.
    Supplied `sample_values` override the agent's configured
    `pre_call_variables` for this preview only — nothing is saved. Useful
    for checking prompt text in the builder UI before publishing.

    **Auth:** bearer JWT required; caller must own the agent.

    **Errors:** `NOT_FOUND` if no such agent exists, or it belongs to
    another caller.
    """
    rendered = await agent_service.render_test(agent_id, auth, payload.sample_values)
    return success_response(data=TestRenderResponse(**rendered))


@router.get(
    "/{agent_id}/prompt/language-switch-preview",
    response_model=SuccessResponse[LanguageSwitchPreviewResponse],
    summary="Preview the language-switch prompt",
)
async def preview_language_switch_prompt(
    agent_id: PydanticObjectId = _AGENT_ID_PATH, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    """Returns exactly what would be sent to the language-switch LLM call
    right now, given the agent's current settings and configured languages.
    `prompt` is `null` when the feature is a no-op for this agent (fewer
    than two recognized languages, or `custom` mode with nothing configured
    yet).

    **Auth:** bearer JWT required; caller must own the agent.

    **Errors:** `NOT_FOUND` if no such agent exists, or it belongs to
    another caller.
    """
    mode, languages, prompt = await agent_service.preview_language_switch_prompt(agent_id, auth)
    return success_response(data=LanguageSwitchPreviewResponse(mode=mode, languages=languages, prompt=prompt))


# --- system prompt versions (create/list/replace/delete; see prompt/version_model.py) ---


@router.post(
    "/{agent_id}/prompt/versions",
    response_model=SuccessResponse[SystemPromptVersionOut],
    summary="Save a new system prompt version",
)
async def create_system_prompt_version(
    agent_id: PydanticObjectId = _AGENT_ID_PATH,
    payload: SystemPromptVersionCreate = ...,
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    """Adds a new entry to the agent's library of saved, reusable
    system-prompt snippets, identified by `prompt_key`. This is independent
    of the agent's live `prompt.system_prompt` text (see
    `PATCH .../prompt/messages`) — saving a version here does not change
    what the agent actually uses; it's a snippet a caller can later copy
    text *from*.

    **Auth:** bearer JWT required; caller must own the agent.

    **Errors:** `NOT_FOUND` if no such agent exists, or it belongs to
    another caller; `CONFLICT` if `prompt_key` is already in use for this
    agent.
    """
    await agent_service.get_owned_agent(agent_id, auth)
    version = await prompt_service.create_system_prompt_version(agent_id, payload, auth.user_id)
    return success_response(code=201, message="System prompt version created", data=_version_out(version))


@router.get(
    "/{agent_id}/prompt/versions",
    response_model=SuccessResponse[list[SystemPromptVersionOut]],
    summary="List saved system prompt versions",
)
async def list_system_prompt_versions(
    agent_id: PydanticObjectId = _AGENT_ID_PATH, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    """Lists every saved system-prompt snippet in the agent's library.

    **Auth:** bearer JWT required; caller must own the agent.

    **Errors:** `NOT_FOUND` if no such agent exists, or it belongs to
    another caller.
    """
    # Ownership check only — the versions themselves live in their own
    # collection (system_prompt_versions), not on AgentConfig.
    await agent_service.get_owned_agent(agent_id, auth, write=False)
    versions = await prompt_service.list_system_prompt_versions(agent_id)
    return success_response(data=[_version_out(v) for v in versions])


@router.patch(
    "/{agent_id}/prompt/versions",
    response_model=SuccessResponse[SystemPromptVersionOut],
    summary="Replace a saved system prompt version's text",
)
async def replace_system_prompt(
    agent_id: PydanticObjectId = _AGENT_ID_PATH,
    payload: SystemPromptReplace = ...,
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    """Overwrites the `system_prompt` text of an existing saved version,
    identified by `prompt_key` in the request body. Only the text changes —
    `prompt_description` isn't settable this way.

    **Auth:** bearer JWT required; caller must own the agent.

    **Errors:** `NOT_FOUND` if no such agent exists, it belongs to another
    caller, or no saved version has this `prompt_key`.
    """
    await agent_service.get_owned_agent(agent_id, auth)
    version = await prompt_service.replace_system_prompt(agent_id, payload)
    return success_response(message="System prompt replaced", data=_version_out(version))


@router.delete(
    "/{agent_id}/prompt/versions/{prompt_key}",
    response_model=SuccessResponse[None],
    summary="Delete a saved system prompt version",
)
async def delete_system_prompt_version(
    agent_id: PydanticObjectId = _AGENT_ID_PATH,
    prompt_key: str = Path(description="The saved version's `prompt_key`."),
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    """Removes one saved system-prompt snippet from the agent's library.
    Nothing on the agent's live config ever points at a saved version, so
    this has no side effects beyond removing the library entry itself.

    **Auth:** bearer JWT required; caller must own the agent.

    **Errors:** `NOT_FOUND` if no such agent exists, it belongs to another
    caller, or no saved version has this `prompt_key`.
    """
    # Ownership check only, same as the other version routes — a version is
    # just a saved library entry now, nothing on AgentConfig ever points at
    # one, so there's nothing else to check before deleting it.
    await agent_service.get_owned_agent(agent_id, auth)
    await prompt_service.delete_system_prompt_version(agent_id, prompt_key)
    return success_response(message="System prompt version deleted")
