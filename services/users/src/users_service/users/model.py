from datetime import datetime, timezone

from beanie import Document
from beanie import PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

from users_service.enums import UserStatus


class User(Document):
    """Identity + status only. A user's role is never global — it comes from
    their per-organization membership (see users_service.memberships), so a
    user can hold a different role in each organization they belong to.
    `is_super_admin` is the one exception: it's a platform-wide flag,
    orthogonal to org membership, not one of the three org-scoped roles.
    """

    email: str
    hashed_password: str
    full_name: str
    is_super_admin: bool = False
    status: UserStatus = UserStatus.ACTIVE
    must_change_password: bool = False
    created_by: PydanticObjectId | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login_at: datetime | None = None

    class Settings:
        name = "users"
        indexes = [
            # Global uniqueness: login takes only an email + password with no
            # org context, so email must resolve unambiguously.
            IndexModel("email", unique=True),
        ]
