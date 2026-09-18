from datetime import datetime

from common.enums import Role
from pydantic import BaseModel, EmailStr, Field

from users_service.enums import UserStatus


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=200)
    role: Role
    # Required when the caller is SUPER_ADMIN (which org to create the user in).
    # Ignored/overridden for org-scoped callers, who may only create within their own org.
    organization_id: str | None = None


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    role: Role | None = None
    status: UserStatus | None = None
    password: str | None = Field(default=None, min_length=8)


class UserSelfUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    password: str | None = Field(default=None, min_length=8)
    current_password: str | None = None


class UserOut(BaseModel):
    id: str
    # organization_id/role reflect the membership in scope for this response
    # (the caller's current org, or the org just acted on) — a user with no
    # resolvable single-org context (e.g. a Super Admin's cross-org listing)
    # gets both as None. See users_service.users.service.
    organization_id: str | None
    email: EmailStr
    full_name: str
    role: Role | None
    is_super_admin: bool
    status: UserStatus
    must_change_password: bool
    created_by: str | None
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None
