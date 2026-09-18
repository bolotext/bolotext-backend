from datetime import datetime, timezone
from typing import Literal

from beanie import Document
from pydantic import Field
from pymongo import IndexModel

AgentStatus = Literal["draft", "published", "disabled"]


class Agent(Document):
    """Core identity only — see agent_configs/model.py's `AgentConfig` for
    everything else (prompt, transcriber, llm, voice persona, etc.), stored
    in its own collection since it's edited far more often, per-section,
    than an agent's name/description/status ever are.
    """

    org_id: str | None = None
    user_id: str
    name: str
    description: str | None = None
    status: AgentStatus = "draft"

    deleted_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "agents"
        indexes = [
            IndexModel("user_id"),
            IndexModel("org_id"),
            IndexModel("status"),
        ]
