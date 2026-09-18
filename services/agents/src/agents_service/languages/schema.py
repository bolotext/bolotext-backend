from pydantic import BaseModel, ConfigDict


class LanguagesUpdate(BaseModel):
    """Body for PUT /agents/{agent_id}/languages — a full replace of the
    agent's configured languages (not a PATCH-style merge: there's only one
    field, so "replace the list" and "set the list" are the same operation).
    Must be non-empty — enforced in agents.service.update_languages, not here
    (a business rule, not a structural one; see that function's docstring).
    """

    model_config = ConfigDict(json_schema_extra={"example": {"languages": ["en-IN", "hi-IN"]}})

    languages: list[str]
