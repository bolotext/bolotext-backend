from pydantic import BaseModel, ConfigDict, Field


class LanguageOption(BaseModel):
    """One selectable language for an STT model — `code` is what to store in
    `transcriber.language`; `language` is the display name."""

    language: str = Field(..., description="Human-readable language name, e.g. `English (India)`.")
    code: str = Field(..., description="Language code to set as `transcriber.language`, e.g. `en-IN`.")


class VoiceOption(BaseModel):
    """One TTS voice with the metadata the voice picker filters on."""

    voice_id: str = Field(..., description="Voice id to store as `voice_persona.voice_id`.")
    label: str = Field(..., description="Human-readable voice name, e.g. `Haley`.")
    gender: str | None = Field(None, description="`female` or `male`, for the voice picker's gender filter.")
    language: str | None = Field(None, description="Language the voice speaks, e.g. `English`.")
    accent: str | None = Field(None, description="Accent, e.g. `American`, where the provider publishes one.")


class ModelInfo(BaseModel):
    """One model (or, under a TTS provider, one voice) offered by a
    provider — an entry in `ProviderInfo.models`."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "model_id": "gpt-4o-mini",
                "label": "GPT-4o mini",
                "description": "Fast, low-cost general-purpose model with function calling.",
                "is_active": True,
                "function_calling": True,
                "supported_languages": [{"language": "English", "code": "en"}],
            }
        }
    )

    model_id: str = Field(..., description="Model id to set as `model_id` on the relevant agent section (llm/transcriber/voice_persona).")
    label: str = Field(..., description="Human-readable name for display in the agent builder.")
    description: str | None = Field(None, description="Short description of the model's characteristics or intended use.")
    is_active: bool = Field(True, description="Whether this model is currently selectable; inactive models are shown for reference only.")
    function_calling: bool = Field(False, description="Whether this model supports function/tool calling (relevant to LLM models only).")
    supported_languages: list[LanguageOption] = Field([], description="Languages this model supports (STT models). Offer these in the language picker and store the chosen `code` as `transcriber.language`.")
    voice_ids: list[str] = Field([], description="Voice ids this model offers (TTS models). Offer these in the voice picker and store the chosen one as `voice_persona.voice_id`.")
    voices: list[VoiceOption] = Field([], description="Optional richer metadata for `voice_ids` (label, gender, language). When present, it lists the same voices as `voice_ids`.")


class ProviderInfo(BaseModel):
    """One LLM/STT/TTS provider and the models (or voices) it offers."""

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
                        "supported_languages": [{"language": "English", "code": "en"}],
                    }
                ],
            }
        }
    )

    provider_id: str = Field(..., description="Provider id to set as `provider_id` on the relevant agent section (llm/transcriber/voice_persona).")
    label: str = Field(..., description="Human-readable name for display in the agent builder.")
    supports_function_calling: bool = Field(False, description="Whether any model from this provider supports function/tool calling (relevant to LLM providers only).")
    multilingual: bool = Field(False, description="Whether this provider supports multiple languages.")
    models: list[ModelInfo] = Field(..., description="Models (LLM/STT) or voices (TTS) this provider offers.")


class ProviderCatalog(BaseModel):
    """The full provider+model registry, grouped by capability — the shape
    returned by `GET /providers`."""

    llm: list[ProviderInfo] = Field(..., description="Available LLM providers and models.")
    stt: list[ProviderInfo] = Field(..., description="Available speech-to-text providers and models.")
    tts: list[ProviderInfo] = Field(..., description="Available text-to-speech providers and voices.")
