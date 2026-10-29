from pydantic import BaseModel, ConfigDict, Field

from agents_service.core.partial import partial_model


class TranscriberSettings(BaseModel):
    """Speech-to-text (ASR) provider and tuning settings for one agent. See
    `GET /providers/stt` for valid `provider_id`/`model_id` combinations."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "provider_id": "gnani",
                "model_id": "gnani-stt-v2",
                "language": "en",
                #"tier": "balanced",
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
    provider_id: str = Field("deepgram", description="STT provider id, e.g. `gnani`. See GET /providers/stt for valid values.")
    model_id: str | None = Field("nova-3", description="STT model id offered by `provider_id`, e.g. `gnani-stt-v2`.")
    language: str = Field("multi", description="Language code the transcriber listens for, e.g. `en-IN`. Must be one of the chosen model's `supported_languages[].code` in GET /providers/stt.")
    #tier: str | None = Field(None, description="Provider-specific quality/cost tier for the model, e.g. `balanced`.")
    allow_interruptions: bool = Field(True, description="Whether the caller can interrupt (barge in on) the agent while it's speaking.")
    min_time_to_barge: float = Field(1.0, description="Minimum seconds the agent must be speaking before a barge-in interruption is honored.")
    background_noise_filtering: bool = Field(True, description="Whether background noise is filtered out before transcription.")
    noise_suppression_level: int = Field(80, description="Aggressiveness of noise suppression, 0-100 (higher suppresses more).")
    inverse_text_normalization: bool = Field(False, description="Whether spoken forms are converted to written forms in the transcript, e.g. \"twenty\" to \"20\".")
    smart_pause: bool = Field(False, description="Whether the transcriber adapts its end-of-speech pause detection to the speaker's pace.")
    max_speech_duration: float = Field(30.0, description="Maximum seconds of continuous speech transcribed as a single utterance before it's cut and finalized.")
    initial_silence_timeout: float = Field(10.0, description="Seconds to wait for the caller to start speaking before treating the turn as silent.")
    speech_segmentation_silence_timeout: float = Field(0.8, description="Seconds of silence that marks the end of an utterance.")
    enable_dtmf: bool = Field(False, description="Whether DTMF (keypad tone) input is recognized during the call.")


TranscriberSettingsUpdate = partial_model(TranscriberSettings)
