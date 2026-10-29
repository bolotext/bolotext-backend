from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


class ApiToken(Document):
    """A non-expiring, revocable service credential (e.g. for the voice agent
    to read agent configs). Only a SHA-256 hash of the token is stored, so a
    DB read never yields a usable token; the plaintext is shown exactly once,
    at creation. Created and revoked only by a Super Admin.
    """

    name: str
    token_prefix: str  # first characters of the token, for recognising it in a list
    token_hash: str
    scopes: list[str]
    created_by: PydanticObjectId
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    revoked: bool = False
    revoked_at: datetime | None = None
    revoked_by: PydanticObjectId | None = None

    class Settings:
        name = "api_tokens"
        indexes = [IndexModel("token_hash", unique=True), IndexModel("created_at")]
