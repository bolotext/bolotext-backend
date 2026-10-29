import re

from beanie import PydanticObjectId
from common.errors import ConflictError, NotFoundError, UnprocessableEntityError

from agents_service.prompt import repository as prompt_repo
from agents_service.prompt.language_switch import render_language_switch_prompt
from agents_service.prompt.schema import AgentPrompt, SystemPromptReplace, SystemPromptVersionCreate
from agents_service.prompt.version_model import MAX_SYSTEM_PROMPT_VERSIONS, SystemPromptVersion

_DYNAMIC_VAR_PATTERN = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")


def referenced_variables(prompt: AgentPrompt) -> set[str]:
    # Deliberately excludes prompt.system_prompt: it's free text edited
    # independently (via .../prompt/messages, same as welcome/ending, but
    # not gated on anything — see AgentPrompt's docstring), and requiring
    # every {{var}} in it to also be pre-declared would make editing the
    # system-prompt-version library (prompt/versions) and this section's
    # pre_call_variables have to stay in lockstep for no real benefit.
    text = f"{prompt.welcome_message} {prompt.ending_message}"
    return set(_DYNAMIC_VAR_PATTERN.findall(text))


def validate_prompt(prompt: AgentPrompt) -> None:
    """Every {{var}} referenced in welcome_message/ending_message must be a
    key in pre_call_variables — called at every save that touches this
    section (.../prompt/messages, PUT .../pre-call-variables, since that's
    also what declares the allowed set now, and everything else that writes
    AgentPrompt), never left for the calling layer to discover. See
    referenced_variables for why system_prompt itself isn't covered.
    """
    missing = sorted(referenced_variables(prompt) - set(prompt.pre_call_variables))
    if missing:
        raise UnprocessableEntityError(
            "Prompt references variables that are not declared in pre_call_variables", {"missing_variables": missing}
        )


def validate_language_switch(prompt: AgentPrompt) -> None:
    """Called at the same save-time points as validate_prompt: a "custom"
    language_switch_mode is meaningless without text to use, so it's rejected
    up front rather than silently rendering nothing at call time.
    """
    if prompt.language_switch_mode == "custom" and not prompt.language_switch_prompt:
        raise UnprocessableEntityError(
            "language_switch_prompt is required when language_switch_mode is 'custom'"
        )


def resolve_language_switch_prompt(prompt: AgentPrompt, languages: list[str]) -> str | None:
    """The prompt that would actually be sent to the language-switch LLM call
    right now, given this agent's mode and configured languages — None if the
    feature doesn't apply (fewer than two recognized languages configured, or
    "custom" with no text set yet). See prompt/language_switch.py.

    `prompt.pre_call_variables` resolves any {{var}} placeholders, but only
    for "custom" mode's caller-authored text — "implicit"/"explicit" render
    a fixed language-detection template with no customer data in it, so
    there's nothing there to substitute. Skipped entirely when
    `pre_call_variables_enabled` is False.
    """
    rendered = render_language_switch_prompt(languages, prompt.language_switch_mode, prompt.language_switch_prompt)
    if rendered and prompt.language_switch_mode == "custom" and prompt.pre_call_variables_enabled and prompt.pre_call_variables:
        defaults = prompt.pre_call_variables
        rendered = _DYNAMIC_VAR_PATTERN.sub(lambda m: defaults.get(m.group(1), m.group(0)), rendered)
    return rendered


def render_test(prompt: AgentPrompt, sample_values: dict[str, str]) -> dict:
    """Dry-run render of the three prompt fields for the agent-builder's
    "test" tab — also what a live call runtime would need to do "resolve
    these variables with the actual values provided before the call
    starts": for each variable declared in prompt.pre_call_variables,
    `sample_values` (this call's real values) wins, falling back to the
    configured default — unless `pre_call_variables_enabled` is False, in
    which case configured defaults are never used — and finally to a
    `<var_name>` placeholder if nothing supplies one.
    """
    defaults = prompt.pre_call_variables if prompt.pre_call_variables_enabled else {}
    used_values = {var: sample_values.get(var) or defaults.get(var) or f"<{var}>" for var in prompt.pre_call_variables}

    def render(text: str) -> str:
        return _DYNAMIC_VAR_PATTERN.sub(lambda m: used_values.get(m.group(1), m.group(0)), text)

    return {
        "welcome_message": render(prompt.welcome_message),
        "system_prompt": render(prompt.system_prompt),
        "ending_message": render(prompt.ending_message),
        "sample_values_used": used_values,
    }


async def create_system_prompt_version(
    agent_id: PydanticObjectId, payload: SystemPromptVersionCreate, created_by: str
) -> SystemPromptVersion:
    if await prompt_repo.get_version(agent_id, payload.prompt_key) is not None:
        raise ConflictError(
            "A system prompt version with this prompt_key already exists for this agent",
            {"prompt_key": payload.prompt_key},
        )

    existing = await prompt_repo.count_versions(agent_id)
    if existing >= MAX_SYSTEM_PROMPT_VERSIONS:
        raise UnprocessableEntityError(
            f"Maximum of {MAX_SYSTEM_PROMPT_VERSIONS} system prompt versions is allowed. "
            "Delete a previous version, then you can create another.",
            {"max_versions": MAX_SYSTEM_PROMPT_VERSIONS, "current_versions": existing},
        )

    return await prompt_repo.create_version(
        agent_id, payload.prompt_key, payload.prompt_description, payload.system_prompt, created_by
    )


async def list_system_prompt_versions(agent_id: PydanticObjectId) -> list[SystemPromptVersion]:
    return await prompt_repo.list_versions(agent_id)


async def replace_system_prompt(agent_id: PydanticObjectId, payload: SystemPromptReplace) -> SystemPromptVersion:
    version = await prompt_repo.get_version(agent_id, payload.prompt_key)
    if version is None:
        raise NotFoundError("System prompt version not found")

    version.system_prompt = payload.system_prompt
    return await prompt_repo.save(version)


async def delete_system_prompt_version(agent_id: PydanticObjectId, prompt_key: str) -> None:
    deleted = await prompt_repo.delete_version(agent_id, prompt_key)
    if not deleted:
        raise NotFoundError("System prompt version not found")


async def delete_all_system_prompt_versions(agent_id: PydanticObjectId) -> None:
    """Called by agents.service.delete_agent as part of its cascade — every
    version, not just one, and never 404s (there may be zero).
    """
    await prompt_repo.delete_all_versions(agent_id)
