from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agents_service.core.partial import partial_model
from agents_service.dynamic_message.schema import DynamicMessageSettings


class AgentPrompt(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "welcome_message": "Hi {{customer_name}}, this is Neha calling from [BANK_A] regarding your loan account.",
                "system_prompt": "You are a polite, firm collections agent. Confirm identity, state the outstanding amount ({{due_amount}}), and offer a payment link.",
                "ending_message": "Thank you for your time, {{customer_name}}. Have a great day.",
                "language_switch_mode": "explicit",
                "language_switch_prompt": None,
                "min_words_for_lang_switch": 2,
                "pre_call_variables": {"customer_name": "", "due_amount": ""},
                "pre_call_variables_enabled": True,
                "dynamic_message": {
                    "dynamic_message_enabled": False,
                    "method": "POST",
                    "url": None,
                    "headers": {},
                },
            }
        }
    )

    # Left as "" (not a bare required str) so `POST /agents` can default-construct
    # this section with just `agent_details.name` supplied — see agents/service.py.
    welcome_message: str = Field(
        "", description="Message the agent opens the call with. May reference `{{variable}}` placeholders."
    )
    # Literal text, stored and used directly — not a reference to anything.
    # `system_prompt_versions` (see version_model.py) is a separate, optional
    # library of reusable snippets a caller can copy text *from* when filling
    # this in; nothing here is validated against it. Same field name as
    # SystemPromptVersion.system_prompt (that one's a saved library entry's
    # text) — the two are otherwise unrelated, don't confuse them.
    system_prompt: str = Field(
        "", description="The agent's live system prompt text. May reference `{{variable}}` placeholders."
    )
    ending_message: str = Field(
        "", description="Message the agent closes the call with. May reference `{{variable}}` placeholders."
    )
    # "implicit"/"explicit" render a built-in template (see
    # prompt/language_switch.py), scoped to just this agent's configured
    # languages (AgentConfig.languages) — "custom" uses language_switch_prompt
    # verbatim instead. See prompt.service.validate_language_switch for the
    # save-time rule this implies (custom requires the field to be set).
    language_switch_mode: Literal["implicit", "explicit", "custom"] = Field(
        "explicit",
        description='How the agent switches languages mid-call: "implicit" (auto-detect, built-in template), '
        '"explicit" (only when the caller asks, built-in template), or "custom" (uses `language_switch_prompt` verbatim).',
    )
    language_switch_prompt: str | None = Field(
        None, description='Prompt text used verbatim when `language_switch_mode` is "custom". Required in that mode.'
    )
    min_words_for_lang_switch: int = Field(
        2, description="Minimum number of words the caller must say in another language before the agent switches."
    )
    # Default values for {{var}} placeholders in welcome_message/the text
    # resolved for system_prompt/ending_message/a custom-mode
    # language_switch_prompt — also the declared set of variables a {{var}}
    # reference must belong to (see prompt.service.validate_prompt). A
    # call's own values (e.g. from a dialer/CRM) still take priority over
    # these — see prompt.service.render_test/resolve_language_switch_prompt
    # and PUT /agents/{id}/pre-call-variables.
    pre_call_variables: dict[str, str] = Field(
        {},
        description="Declared `{{variable}}` names and their default values. Every `{{variable}}` reference in "
        "this agent's prompt text must be declared here. A call's own values (e.g. from a dialer/CRM) override these.",
    )
    # Toggles whether pre_call_variables is actually used to resolve {{var}}
    # placeholders (see prompt.service.render_test/resolve_language_switch_
    # prompt) — defaults to True so existing behavior is unchanged unless a
    # caller explicitly turns it off via PUT /agents/{id}/pre-call-variables.
    pre_call_variables_enabled: bool = Field(
        True, description="Whether `pre_call_variables` is used to resolve `{{variable}}` placeholders at call time."
    )
    # An external API the agent can call mid-call for a dynamic message —
    # storage/config only, see dynamic_message/schema.py's docstring.
    dynamic_message: DynamicMessageSettings = Field(
        DynamicMessageSettings(),
        description="Settings for an external API the agent can call mid-call to fetch a dynamic message.",
    )


AgentPromptUpdate = partial_model(AgentPrompt)


class PromptMessages(BaseModel):
    """The subset of AgentPrompt covered by the dedicated (and, since the
    generic PATCH .../prompt was removed, only) PATCH .../prompt/messages
    route — welcome/system/ending only, none of the language-switch fields,
    pre_call_variables, or dynamic_message (see LanguageSwitchSettings for
    the former; PUT .../pre-call-variables and .../dynamic-message for the
    latter two — every AgentPrompt field is covered by exactly one of these
    four routes).
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "welcome_message": "Hi {{customer_name}}, this is Neha calling from [BANK_A].",
                "system_prompt": "You are a polite, firm collections agent.",
                "ending_message": "Thank you for your time, {{customer_name}}. Have a great day.",
            }
        }
    )

    welcome_message: str = Field("", description="Message the agent opens the call with. May reference `{{variable}}` placeholders.")
    system_prompt: str = Field("", description="The agent's live system prompt text. May reference `{{variable}}` placeholders.")  # literal text — see AgentPrompt.system_prompt's docstring
    ending_message: str = Field("", description="Message the agent closes the call with. May reference `{{variable}}` placeholders.")


PromptMessagesUpdate = partial_model(PromptMessages)


class LanguageSwitchSettings(BaseModel):
    """The subset of AgentPrompt covered by the dedicated PATCH .../prompt/
    language-switch route — see PromptMessages for its sibling.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"language_switch_mode": "implicit", "language_switch_prompt": None, "min_words_for_lang_switch": 2}
        }
    )

    language_switch_mode: Literal["implicit", "explicit", "custom"] = Field(
        "explicit",
        description='How the agent switches languages mid-call: "implicit" (auto-detect, built-in template), '
        '"explicit" (only when the caller asks, built-in template), or "custom" (uses `language_switch_prompt` verbatim).',
    )
    language_switch_prompt: str | None = Field(
        None, description='Prompt text used verbatim when `language_switch_mode` is "custom". Required in that mode.'
    )
    min_words_for_lang_switch: int = Field(
        2, description="Minimum number of words the caller must say in another language before the agent switches."
    )


LanguageSwitchSettingsUpdate = partial_model(LanguageSwitchSettings)


class TestRenderRequest(BaseModel):
    """Body for POST /agents/{agent_id}/test."""

    model_config = ConfigDict(json_schema_extra={"example": {"sample_values": {"customer_name": "Ramesh Kumar"}}})

    sample_values: dict[str, str] = Field(
        {}, description="Values to substitute for `{{variable}}` placeholders in this preview, overriding the agent's configured `pre_call_variables`."
    )


class TestRenderResponse(BaseModel):
    """Rendered prompt text returned by POST /agents/{agent_id}/test."""

    welcome_message: str = Field(description="Welcome message with `{{variable}}` placeholders resolved.")
    system_prompt: str = Field(description="System prompt with `{{variable}}` placeholders resolved.")
    ending_message: str = Field(description="Ending message with `{{variable}}` placeholders resolved.")
    sample_values_used: dict[str, str] = Field(description="The actual variable values used for this render (configured defaults merged with any `sample_values` supplied).")


class SystemPromptVersionCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "prompt_key": "prompt_v1",
                "prompt_description": "Original, firm-but-polite collections tone.",
                "system_prompt": "You are a polite, firm collections agent. Confirm identity, state the outstanding amount ({{due_amount}}), and offer a payment link.",
            }
        }
    )

    prompt_key: str = Field(description="Unique key identifying this saved version within the agent's library.")
    prompt_description: str | None = Field(None, description="Optional human-readable note about this version, e.g. its tone or intended use.")
    system_prompt: str = Field(description="The saved system prompt text.")


class SystemPromptReplace(BaseModel):
    """Body for PATCH .../prompt/versions — replaces one existing version's
    `system_prompt` text in place, identified by `prompt_key` (here in the
    body, not a path param). `prompt_description` isn't settable this way —
    this replaces the text only, nothing else about the version.
    """

    model_config = ConfigDict(
        json_schema_extra={"example": {"prompt_key": "prompt_v1", "system_prompt": "You are a polite, firm collections agent."}}
    )

    prompt_key: str = Field(description="Key of the existing saved version whose text to replace.")
    system_prompt: str = Field(description="New system prompt text for this saved version.")


class SystemPromptVersionOut(BaseModel):
    """One saved system-prompt version, as returned by the .../prompt/versions routes."""

    prompt_key: str = Field(description="Unique key identifying this saved version within the agent's library.")
    prompt_description: str | None = Field(description="Optional human-readable note about this version.")
    system_prompt: str = Field(description="The saved system prompt text.")
    created_by: str = Field(description="Id of the user who created this version.")
    created_at: datetime = Field(description="When this version was created (UTC).")
    updated_at: datetime = Field(description="When this version's text was last replaced (UTC).")


class LanguageSwitchPreviewResponse(BaseModel):
    """GET .../prompt/language-switch-preview — what would actually be sent
    to the language-switch LLM call right now. `prompt` is None when the
    feature is a no-op: fewer than two of AgentConfig.languages are
    recognized (see prompt/language_switch.py), or mode is "custom" with
    nothing configured yet.
    """

    mode: Literal["implicit", "explicit", "custom"] = Field(description="The agent's configured language-switch mode.")
    languages: list[str] = Field(description="The agent's configured languages considered for switching.")
    prompt: str | None = Field(description="The rendered language-switch prompt, or `null` if the feature is currently a no-op for this agent.")
