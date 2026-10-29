from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from agents_service.core.partial import partial_model


class VoicePersonaSection(BaseModel):
    """A single voice-persona configuration for the agent — not a list to
    pick from; one agent has one voice. See `GET /providers/tts` for valid
    `provider_id`/`voice_id` combinations.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "gender": "female",
                "provider_id": "elevenlabs",
                "model_id": "eleven_multilingual_v2",
                "voice_id": "21m00Tcm4TlvDq8ikWAM",
                "rate_of_speech": 1.0,
                "use_ambient_sound": False,
                "ambient_sound_volume": 0.2,
                "ambient_sound_type": None,
            }
        }
    )

    gender: Literal["male", "female", "neutral"] | None = Field("female", description="Voice gender, used to help pick/filter a `voice_id`.")
    # provider_id/voice_id default to "" (not bare required strs) so a fresh
    # draft agent can default-construct this section — see agents/service.py.
    provider_id: str = Field("deepgram", description="TTS provider id, e.g. `elevenlabs`. See GET /providers/tts for valid values.")
    model_id: str | None = Field("flux", description="TTS model id offered by `provider_id`. See GET /providers/tts.")
    voice_id: str = Field("flux-shreya-hi", description="Voice id offered by the chosen `model_id`.")
    rate_of_speech: float = Field(1.0, description="Speaking rate multiplier; 1.0 is the provider's normal pace.")
    use_ambient_sound: bool = Field(False, description="Whether background ambient sound is mixed into the agent's speech.")
    ambient_sound_volume: float = Field(0.2, description="Ambient sound mix volume, 0.0-1.0. Only used when `use_ambient_sound` is true.")
    ambient_sound_type: str | None = Field(None, description="Which ambient sound to play, e.g. `office`. Only used when `use_ambient_sound` is true.")


VoicePersonaSectionUpdate = partial_model(VoicePersonaSection)
