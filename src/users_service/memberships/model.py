from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from common.enums import Role
from pydantic import Field
from pymongo import IndexModel


class OrganizationMembership(Document):
    """A user's role within one organization. A user may hold a different
    membership (and therefore a different role) in each organization they
    belong to — see users_service.users.service.ORG_ASSIGNABLE_ROLES for the
    roles a membership may hold. SUPER_ADMIN is not a membership role: it's
    the platform-wide `User.is_super_admin` flag instead, orthogonal to org
    membership.
    """

    user_id: PydanticObjectId
    organization_id: PydanticObjectId
    role: Role
    created_by: PydanticObjectId | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "organization_memberships"
        indexes = [
            IndexModel([("user_id", 1), ("organization_id", 1)], unique=True),
            IndexModel("organization_id"),
        ]
