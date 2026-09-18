"""An optional library of reusable `system_prompt` texts per agent, kept in
its own collection. Independent of `AgentPrompt.system_prompt` (in
agent_configs) — that field is plain text, stored and used directly, not
validated against or resolved from this collection in any way. A version
row is just somewhere to save a snippet for later reuse/copy-paste; nothing
else in this service reads or writes AgentConfig because of it.

Capped at MAX_SYSTEM_PROMPT_VERSIONS per agent; creating past the cap is
rejected until an old version is deleted — see prompt/service.py.
"""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

MAX_SYSTEM_PROMPT_VERSIONS = 5


class SystemPromptVersion(Document):
    agent_id: PydanticObjectId
    prompt_key: str  # unique per agent; identifies this saved snippet
    prompt_description: str | None = None
    system_prompt: str
    created_by: str  # user_id of the caller who created this version
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "system_prompt_versions"
        indexes = [IndexModel([("agent_id", 1), ("prompt_key", 1)], unique=True)]
