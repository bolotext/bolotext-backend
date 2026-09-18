from typing import Literal

from pydantic import BaseModel, ConfigDict

from agents_service.core.partial import partial_model


class VoicePersonaSection(BaseModel):
    """A single voice-persona configuration for the agent — not a list to
    pick from; one agent has one voice.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "gender": "female",
                "provider_id": "elevenlabs",
                "voice_id": "21m00Tcm4TlvDq8ikWAM",
                "rate_of_speech": 1.0,
                "use_ambient_sound": False,
                "ambient_sound_volume": 0.2,
                "ambient_sound_type": None,
            }
        }
    )

    gender: Literal["male", "female", "neutral"] | None = None
    # provider_id/voice_id default to "" (not bare required strs) so a fresh
    # draft agent can default-construct this section — see agents/service.py.
    provider_id: str = ""
    voice_id: str = ""
    rate_of_speech: float = 1.0
    use_ambient_sound: bool = False
    ambient_sound_volume: float = 0.2
    ambient_sound_type: str | None = None


VoicePersonaSectionUpdate = partial_model(VoicePersonaSection)
