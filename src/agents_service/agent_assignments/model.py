"""Which agents a Developer can see/act on within an org — see agents.service's
docstring on `_authorize_agent_access` for how this is consumed. Admin and QA
never consult this collection (Admin has full access, QA is org-wide
view-only); it only gates Developer access.
"""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


class AgentAssignment(Document):
    agent_id: PydanticObjectId
    user_id: str
    org_id: str | None = None
    assigned_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "agent_assignments"
        indexes = [
            IndexModel([("agent_id", 1), ("user_id", 1)], unique=True),
            IndexModel("user_id"),
        ]
