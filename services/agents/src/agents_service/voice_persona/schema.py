from typing import Literal

from pydantic import BaseModel, ConfigDict

from agents_service.core.partial import partial_model


class VoicePersona(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "persona_id": "persona-1",
                "name": "Neha",
                "gender": "female",
                "provider_id": "elevenlabs",
                "voice_id": "21m00Tcm4TlvDq8ikWAM",
                "language": "en-IN",
                "rate_of_speech": 1.0,
                "use_background_audio": False,
                "background_audio_path": None,
                "background_audio_volume": 0.2,
                "is_default": True,
            }
        }
    )

    persona_id: str
    name: str
    gender: Literal["male", "female", "neutral"] | None = None
    provider_id: str
    voice_id: str
    language: str = "en-IN"
    rate_of_speech: float = 1.0
    use_background_audio: bool = False
    background_audio_path: str | None = None
    background_audio_volume: float = 0.2
    is_default: bool = True


class VoicePersonaSection(BaseModel):
    personas: list[VoicePersona] = []


VoicePersonaSectionUpdate = partial_model(VoicePersonaSection)
