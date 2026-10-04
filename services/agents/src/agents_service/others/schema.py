from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agents_service.core.partial import partial_model


class VoicemailDetectionConfig(BaseModel):
    """Whether/how the agent detects it has reached voicemail on an
    outbound call and what it says if so."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "enabled": True,
                "max_detection_retries": 2,
                "voicemail_response": "Hi, this is [BANK_A] calling. Please call us back at your convenience.",
            }
        }
    )

    enabled: bool = Field(False, description="Whether the agent attempts to detect voicemail on outbound calls.")
    max_detection_retries: int = Field(2, description="Maximum number of detection attempts before giving up.")
    voicemail_response: str | None = Field(None, description="Message the agent leaves if it detects voicemail.")


class CallTransferConfig(BaseModel):
    """Whether/how the agent can transfer a call to a human specialist."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "enabled": True,
                "default_transfer_message": "Let me connect you to a specialist.",
                "tta_type": "phone",
                "send_transcript_with_transfer": True,
            }
        }
    )

    enabled: bool = Field(False, description="Whether the agent can transfer calls to a human.")
    default_transfer_message: str | None = Field(None, description="Message the agent says to the caller before transferring.")
    tta_type: Literal["phone", "sip"] = Field("phone", description="Transport used to reach the transfer target: a phone number or a SIP endpoint.")
    send_transcript_with_transfer: bool = Field(False, description="Whether the call transcript so far is sent along with the transfer.")


class OthersSettings(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "voicemail_detection": {"enabled": True, "max_detection_retries": 2, "voicemail_response": None},
                "call_transfer": {
                    "enabled": False,
                    "default_transfer_message": None,
                    "tta_type": "phone",
                    "send_transcript_with_transfer": False,
                },
            }
        }
    )

    voicemail_detection: VoicemailDetectionConfig | None = Field(None, description="Voicemail detection settings; unset disables the feature.")
    call_transfer: CallTransferConfig | None = Field(None, description="Call transfer settings; unset disables the feature.")


OthersSettingsUpdate = partial_model(OthersSettings)
