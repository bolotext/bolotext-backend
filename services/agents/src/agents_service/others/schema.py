from typing import Literal

from pydantic import BaseModel, ConfigDict

from agents_service.core.partial import partial_model


class PrecallVariable(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "variable": "customer_name",
                "sample_value": "Ramesh Kumar",
                "description": "Full name pulled from the dialer's contact list.",
            }
        }
    )

    variable: str
    sample_value: str | None = None
    description: str | None = None


class NoResponseConfig(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "silence_wait_time": 10,
                "max_retries": 2,
                "no_response_message": "Sorry, I couldn't hear you. Are you still there?",
                "call_disconnection_message": "I'll disconnect now since we can't hear you. Goodbye.",
            }
        }
    )

    silence_wait_time: int = 10
    max_retries: int = 2
    no_response_message: str
    call_disconnection_message: str


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
                "precall_variables": [
                    {"variable": "customer_name", "sample_value": "Ramesh Kumar", "description": None}
                ],
                "no_response_config": {
                    "silence_wait_time": 10,
                    "max_retries": 2,
                    "no_response_message": "Sorry, I couldn't hear you. Are you still there?",
                    "call_disconnection_message": "I'll disconnect now. Goodbye.",
                },
                "voicemail_detection": {"enabled": True, "max_detection_retries": 2, "voicemail_response": None},
                "call_transfer": {
                    "enabled": False,
                    "default_transfer_message": None,
                    "tta_type": "phone",
                    "send_transcript_with_transfer": False,
                },
                "post_call_trigger_url": "https://example.com/webhooks/call-ended",
            }
        }
    )

    precall_variables: list[PrecallVariable] = []
    no_response_config: NoResponseConfig | None = None
    voicemail_detection: VoicemailDetectionConfig | None = None
    call_transfer: CallTransferConfig | None = None
    post_call_trigger_url: str | None = None


OthersSettingsUpdate = partial_model(OthersSettings)
