from datetime import datetime, timezone

from beanie import Document
from pydantic import ConfigDict, Field
from pymongo import IndexModel


class CallLog(Document):
    """One finished call of a voice agent, stored exactly as the voice runtime
    posted it (see `CallLogIn`). Only the keys we query on are declared; every
    other field the runtime sends (`conversation_log`, `token_usage`,
    `hangup_reason`, `callStartTime`, …) is kept as an extra. Nothing is
    derived at write time; list/detail views compute what they show on read.
    """

    model_config = ConfigDict(extra="allow")

    bot_id: str  # the voice agent's id
    org_id: str | None = None  # copied from the agent, for tenant scoping
    conversation_id: str | None = None  # the call's session id
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "call_logs"
        indexes = [
            IndexModel([("bot_id", 1), ("callStartTime", -1)]),
            IndexModel("org_id"),
            # A retried POST for the same conversation updates instead of duplicating.
            IndexModel([("bot_id", 1), ("conversation_id", 1)], unique=True, partialFilterExpression={"conversation_id": {"$type": "string"}}),
        ]
