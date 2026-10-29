from datetime import datetime, timezone
from typing import Any

from beanie import Document
from pydantic import Field
from pymongo import IndexModel


class CallLog(Document):
    """One finished call of a voice agent, as posted by the voice runtime.
    The listing fields are lifted out of `interaction` so they can be filtered
    and sorted; `interaction` itself (details, token usage, the whole
    conversation journey) is kept exactly as received.
    """

    agent_id: str
    org_id: str | None = None  # copied from the agent, for tenant scoping
    session_id: str | None = None
    source: str | None = None  # phone / website / personalized_link
    direction: str | None = None  # inbound / outbound
    status: str | None = None  # completed / missed / busy / failed …
    test: bool = False
    duration: str | None = None  # "m:ss" as reported
    duration_seconds: int | None = None
    started_at: datetime | None = None
    from_phone: str | None = None
    to_phone: str | None = None
    web_uuid: str | None = None
    recording_sid: str | None = None
    hangup_reason: str | None = None  # the end reason, for the list
    messages: int = 0  # spoken turns in the journey
    interaction: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "call_logs"
        indexes = [
            IndexModel([("agent_id", 1), ("started_at", -1)]),
            IndexModel("org_id"),
            # A retried POST for the same session updates instead of duplicating.
            IndexModel([("agent_id", 1), ("session_id", 1)], unique=True, partialFilterExpression={"session_id": {"$type": "string"}}),
        ]
