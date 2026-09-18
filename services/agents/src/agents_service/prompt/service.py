import re

from beanie import PydanticObjectId
from common.errors import NotFoundError, UnprocessableEntityError

from agents_service.prompt import repository as prompt_repo
from agents_service.prompt.schema import AgentPrompt
from agents_service.prompt.version_model import MAX_SYSTEM_PROMPT_VERSIONS, SystemPromptVersion

_DYNAMIC_VAR_PATTERN = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")


def referenced_dynamic_variables(prompt: AgentPrompt) -> set[str]:
    text = f"{prompt.welcome_message} {prompt.system_prompt} {prompt.ending_message}"
    return set(_DYNAMIC_VAR_PATTERN.findall(text))


def validate_prompt(prompt: AgentPrompt) -> None:
    """Every {{var}} referenced in the three message fields must be declared
    in dynamic_variables — called at save time (PATCH .../prompt and PUT
    .../agents/{id}), never left for the calling layer to discover.
    """
    missing = sorted(referenced_dynamic_variables(prompt) - set(prompt.dynamic_variables))
    if missing:
        raise UnprocessableEntityError(
            "Prompt references dynamic variables that are not declared", {"missing_variables": missing}
        )


def render_test(prompt: AgentPrompt, sample_values: dict[str, str]) -> dict:
    """Dry-run render of the three prompt fields for the agent-builder's
    "test" tab: undeclared samples fall back to a `<var_name>` placeholder.
    """
    used_values = {var: sample_values.get(var, f"<{var}>") for var in prompt.dynamic_variables}

    def render(text: str) -> str:
        return _DYNAMIC_VAR_PATTERN.sub(lambda m: used_values.get(m.group(1), m.group(0)), text)

    return {
        "welcome_message": render(prompt.welcome_message),
        "system_prompt": render(prompt.system_prompt),
        "ending_message": render(prompt.ending_message),
        "sample_values_used": used_values,
    }


async def record_system_prompt_version_if_changed(
    agent_id: PydanticObjectId, old_system_prompt: str, new_system_prompt: str, created_by: str
) -> None:
    """Called whenever a save would change `system_prompt` (PATCH .../prompt
    or PUT .../agents/{id}) — never for saves that leave it untouched, so
    editing welcome_message/ending_message alone never touches the cap.

    Raises UnprocessableEntityError, blocking the whole save, if the agent
    already has MAX_SYSTEM_PROMPT_VERSIONS saved revisions: the caller must
    delete one (DELETE .../prompt/versions/{version}) before saving again.
    """
    if new_system_prompt == old_system_prompt:
        return

    existing = await prompt_repo.count_versions(agent_id)
    if existing >= MAX_SYSTEM_PROMPT_VERSIONS:
        raise UnprocessableEntityError(
            f"Maximum of {MAX_SYSTEM_PROMPT_VERSIONS} system prompt versions is allowed. "
            "Delete a previous version, then you can save.",
            {"max_versions": MAX_SYSTEM_PROMPT_VERSIONS, "current_versions": existing},
        )

    await prompt_repo.create_version(agent_id, new_system_prompt, created_by)


async def list_system_prompt_versions(agent_id: PydanticObjectId) -> list[SystemPromptVersion]:
    return await prompt_repo.list_versions(agent_id)


async def delete_system_prompt_version(agent_id: PydanticObjectId, version: int) -> None:
    deleted = await prompt_repo.delete_version(agent_id, version)
    if not deleted:
        raise NotFoundError("System prompt version not found")
