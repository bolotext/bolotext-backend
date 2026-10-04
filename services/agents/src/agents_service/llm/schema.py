from pydantic import BaseModel, ConfigDict, Field

from agents_service.core.partial import partial_model


class LLMSettings(BaseModel):
    """LLM provider and generation settings for one agent. See
    `GET /providers/llm` for valid `provider_id`/`model_id` combinations."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "provider_id": "openai",
                "model_id": "gpt-4o-mini",
                "temperature": 0.2,
                "max_tokens": 300,
                "knowledge_base_ids": [],
            }
        }
    )

    # provider_id/model_id default to "" (not bare required strs) so a fresh
    # draft agent can default-construct this section — see agents/service.py.
    provider_id: str = Field("", description="LLM provider id, e.g. `openai`. See GET /providers/llm for valid values.")
    model_id: str = Field("", description="LLM model id offered by `provider_id`, e.g. `gpt-4o-mini`.")
    temperature: float = Field(0.2, description="Sampling temperature passed to the LLM; higher values produce more varied responses.")
    max_tokens: int = Field(300, description="Maximum number of tokens the LLM may generate per response.")
    knowledge_base_ids: list[str] = Field([], description="IDs of knowledge bases the agent can retrieve context from when generating a response.")


LLMSettingsUpdate = partial_model(LLMSettings)
