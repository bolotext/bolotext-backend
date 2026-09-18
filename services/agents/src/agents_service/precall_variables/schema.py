from pydantic import BaseModel, ConfigDict


class PreCallVariablesUpdate(BaseModel):
    """Body for PUT /agents/{agent_id}/pre-call-variables — a full replace of
    the agent's pre-call variable defaults (not a PATCH-style merge: same
    reasoning as LanguagesUpdate — these two fields together are the whole
    of what this route owns, so "replace" and "set" are the same
    operation). Values are used to resolve {{var}} placeholders in
    welcome_message/system_prompt/ending_message/the custom-mode language-
    switch prompt whenever a call doesn't supply its own override — see
    prompt.service.render_test/resolve_language_switch_prompt.
    `pre_call_variables_enabled` toggles that resolution on/off entirely.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "pre_call_variables": {
                    "customer_name": "",
                    "customer_id": "",
                    "order_id": "",
                    "company_name": "",
                },
                "pre_call_variables_enabled": True,
            }
        }
    )

    pre_call_variables: dict[str, str]
    pre_call_variables_enabled: bool = True
