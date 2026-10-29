from datetime import datetime, timezone
from typing import Literal

from beanie import Document
from pydantic import Field
from pymongo import IndexModel

AgentStatus = Literal["active", "inactive"]


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
    # An agent is usable as soon as it's created — no draft/publish gate.
    # See agents_service.agents.service.update_status/activate_agent/
    # deactivate_agent and PATCH|POST /agents/{id}/status|activate|deactivate.
    status: AgentStatus = "active"

    # No soft-delete: DELETE /agents/{id} removes this document outright —
    # see agents.service.delete_agent, which also cascades to every
    # AgentConfig and SystemPromptVersion row for this agent.
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "agents"
        indexes = [
            IndexModel("user_id"),
            IndexModel("org_id"),
            IndexModel("status"),
        ]
