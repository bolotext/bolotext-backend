from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CallLogIn(BaseModel):
    """What the voice runtime posts when a call ends."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "agent_id": "6ae2fcd6bc254d03a880f339",
                "call_payload": {
                    "interaction": {
                        "source": "website",
                        "direction": "inbound",
                        "details": {"duration": "0:24", "session_id": "RM_abc", "start_at": "2026-10-29 12:32:02"},
                        "test": True,
                        "token_usage": {"llm_input_token": 742},
                        "interaction_journey": [],
                        "status": "completed",
                    }
                },
            }
        }
    )

    agent_id: str = Field(..., min_length=1, max_length=64, description="The voice agent the call belongs to.")
    call_payload: dict[str, Any] = Field(..., description="`{ \"interaction\": { … } }` exactly as the runtime builds it.")


class CallLogStored(BaseModel):
    id: str
    agent_id: str
    session_id: str | None
    created: bool = Field(description="False when an existing log for the same session was updated.")


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
    interaction: dict[str, Any] = Field(description="The stored interaction: details, token usage and the full conversation journey.")
