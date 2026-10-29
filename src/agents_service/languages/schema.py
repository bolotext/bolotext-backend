from pydantic import BaseModel, ConfigDict, Field


class LanguagesUpdate(BaseModel):
    """Body for PUT /agents/{agent_id}/languages — a full replace of the
    agent's configured languages (not a PATCH-style merge: there's only one
    field, so "replace the list" and "set the list" are the same operation).
    Must be non-empty — enforced in agents.service.update_languages, not here
    (a business rule, not a structural one; see that function's docstring).
    """

    model_config = ConfigDict(json_schema_extra={"example": {"languages": ["en-IN", "hi-IN"]}})

    languages: list[str] = Field(
        description="Full list of BCP-47 language codes the agent should support (e.g. `en-IN`, `hi-IN`). "
        "Replaces the existing list entirely; must be non-empty."
    )


class LanguageOut(BaseModel):
    code: str = Field(description="BCP-47 language code to send in `PUT /agents/{id}/languages`, e.g. `hi-IN`.")
    name: str = Field(description="Display name, e.g. `Hindi`.")
