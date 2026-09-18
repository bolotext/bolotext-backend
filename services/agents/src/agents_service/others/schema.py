from typing import Literal

from pydantic import BaseModel, ConfigDict

from agents_service.core.partial import partial_model


class VoicemailDetectionConfig(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "enabled": True,
                "max_detection_retries": 2,
                "voicemail_response": "Hi, this is [BANK_A] calling. Please call us back at your convenience.",
            }
        }
    )

    enabled: bool = False
    max_detection_retries: int = 2
    voicemail_response: str | None = None


class CallTransferConfig(BaseModel):
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

    enabled: bool = False
    default_transfer_message: str | None = None
    tta_type: Literal["phone", "sip"] = "phone"
    send_transcript_with_transfer: bool = False


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

    voicemail_detection: VoicemailDetectionConfig | None = None
    call_transfer: CallTransferConfig | None = None


OthersSettingsUpdate = partial_model(OthersSettings)
