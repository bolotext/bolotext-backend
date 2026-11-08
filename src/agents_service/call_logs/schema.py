from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CallLogIn(BaseModel):
    """The call-log document the voice runtime posts when a call ends. Stored
    as received: apart from `bot_id` every field is optional and unknown fields
    are kept."""

    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "example": {
                "conversation_id": "RM_e277X9c8dfbX",
                "bot_id": "6ae2fcd6bc254d03a880f339",
                "bot_type": "voice_inbound",
                "time_zone": "Asia/Kolkata",
                "call_status": "COMPLETED",
                "callType": "Inbound",
                "callStartTime": "2026-10-29 19:33:41",
                "is_test": True,
                "source": "website",
                "duration": "0:36",
                "web_uuid": "testing-web-token",
                "hangup_reason": {"end_reason": "tts_error", "error": "tts_error", "type": "close", "reason": "user_initiated"},
                "token_usage": {"llm_input_token": 747, "llm_output_token": 51, "stt_audio_duration": 35, "tts_characters_count": 195},
                "conversation_log": [],
            }
        },
    )

    bot_id: str = Field(..., min_length=1, max_length=64, description="The voice agent the call belongs to.")
    conversation_id: str | None = Field(None, description="The call's session id; posting it again updates the stored log.")


class CallUsageIn(BaseModel):
    """What the voice runtime posts, once per call, after the call log is stored,
    so the usage dashboard counts the call. The runtime sends it only when the
    log was newly created, so a retried log is not counted twice."""

    bot_id: str = Field(..., min_length=1, max_length=64, description="The voice agent the call belongs to.")
    day: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="UTC day of the call, YYYY-MM-DD.")
    is_test: bool = False
    environment: str | None = None
    models: dict[str, dict[str, Any]] | None = Field(None, description="`{stt|llm|tts: {provider_id, model_id}}` the call ran on.")
    token_usage: dict[str, Any] = Field(..., description="The call's `token_usage` block.")


class CallLogStored(BaseModel):
    id: str
    agent_id: str
    session_id: str | None
    created: bool = Field(description="False when an existing log for the same conversation was updated.")


class CallLogSummary(BaseModel):
    id: str
    agent_id: str
    session_id: str | None
    source: str | None
    direction: str | None
    status: str | None
    test: bool
    duration: str | None
    duration_seconds: int | None
    started_at: datetime | None
    from_phone: str | None
    to_phone: str | None
    web_uuid: str | None
    recording_sid: str | None
    hangup_reason: str | None
    messages: int
    created_at: datetime


class CallLogListOut(BaseModel):
    items: list[CallLogSummary]
    total: int


class CallLogOut(CallLogSummary):
    log: dict[str, Any] = Field(description="The stored call-log document: details, token usage, hang-up reason and the full `conversation_log`.")
