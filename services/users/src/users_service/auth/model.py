from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


class RefreshToken(Document):
    user_id: PydanticObjectId
    # Which org session this refresh token is pinned to (None for a Super
    # Admin session) — /auth/refresh re-mints the access token for this same
    # org, so switching orgs (see auth/service.py::switch_organization)
    # always issues a fresh refresh token rather than mutating this one.
    organization_id: PydanticObjectId | None = None
    token_hash: str
    expires_at: datetime
    revoked: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "refresh_tokens"
        indexes = [
            IndexModel("user_id"),
            IndexModel("token_hash", unique=True),
            IndexModel("expires_at", expireAfterSeconds=0),
        ]
