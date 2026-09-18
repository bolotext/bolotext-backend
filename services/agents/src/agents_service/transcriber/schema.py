from pydantic import BaseModel, ConfigDict

from agents_service.core.partial import partial_model


class TranscriberSettings(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "provider_id": "gnani",
                "model_id": "gnani-stt-v2",
                "tier": "balanced",
                "allow_interruptions": True,
                "min_time_to_barge": 1.2,
                "background_noise_filtering": True,
                "noise_suppression_level": 80,
                "inverse_text_normalization": False,
                "smart_pause": False,
                "max_speech_duration": 30.0,
                "initial_silence_timeout": 10.0,
                "speech_segmentation_silence_timeout": 0.8,
                "enable_dtmf": False,
            }
        }
    )

    # provider_id defaults to "" (not a bare required str) so a fresh draft
    # agent can default-construct this section — see agents/service.py.
    provider_id: str = ""
    model_id: str | None = None
    tier: str | None = None
    allow_interruptions: bool = True
    min_time_to_barge: float = 1.2
    background_noise_filtering: bool = True
    noise_suppression_level: int = 80
    inverse_text_normalization: bool = False
    smart_pause: bool = False
    max_speech_duration: float = 30.0
    initial_silence_timeout: float = 10.0
    speech_segmentation_silence_timeout: float = 0.8
    enable_dtmf: bool = False


TranscriberSettingsUpdate = partial_model(TranscriberSettings)
