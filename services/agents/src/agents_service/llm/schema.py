from pydantic import BaseModel, ConfigDict

from agents_service.core.partial import partial_model


class LLMSettings(BaseModel):
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
    provider_id: str = ""
    model_id: str = ""
    temperature: float = 0.2
    max_tokens: int = 300
    knowledge_base_ids: list[str] = []


LLMSettingsUpdate = partial_model(LLMSettings)
