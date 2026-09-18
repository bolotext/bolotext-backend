from pydantic import BaseModel, ConfigDict


class ModelInfo(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "model_id": "gpt-4o-mini",
                "label": "GPT-4o mini",
                "description": "Fast, low-cost general-purpose model with function calling.",
                "is_active": True,
                "function_calling": True,
                "supported_languages": ["en"],
            }
        }
    )

    model_id: str
    label: str
    description: str | None = None
    is_active: bool = True
    function_calling: bool = False
    supported_languages: list[str] = []


class ProviderInfo(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "provider_id": "openai",
                "label": "OpenAI",
                "supports_function_calling": True,
                "multilingual": True,
                "models": [
                    {
                        "model_id": "gpt-4o-mini",
                        "label": "GPT-4o mini",
                        "is_active": True,
                        "function_calling": True,
                        "supported_languages": ["en"],
                    }
                ],
            }
        }
    )

    provider_id: str
    label: str
    supports_function_calling: bool = False
    multilingual: bool = False
    models: list[ModelInfo]


class ProviderCatalog(BaseModel):
    llm: list[ProviderInfo]
    stt: list[ProviderInfo]
    tts: list[ProviderInfo]
