"""A bounded revision history for one field — `system_prompt` — rather than
the whole `AgentConfig` (see agent_configs/model.py's docstring for why: it
changes too often, and is edited from too many places, for a whole-document
snapshot-per-save to be useful). Capped at MAX_SYSTEM_PROMPT_VERSIONS per
agent; saving past the cap is rejected until an old version is deleted — see
prompt/service.py.
"""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

MAX_SYSTEM_PROMPT_VERSIONS = 5


class SystemPromptVersion(Document):
    agent_id: PydanticObjectId
    version: int  # per-agent, monotonically increasing; never reused after a delete
    system_prompt: str
    created_by: str  # user_id of the caller who saved this revision
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "system_prompt_versions"
        indexes = [IndexModel([("agent_id", 1), ("version", 1)], unique=True)]
