from datetime import datetime

from common.enums import Role
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from users_service.enums import UserStatus


class UserCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "new.user@example.com",
                "password": "<password>",
                "full_name": "Jane Doe",
                "role": "DEVELOPER",
            }
        }
    )

    email: EmailStr = Field(description="The new user's email address; must be unique across the platform.")
    password: str = Field(min_length=8, description="Initial password (min. 8 characters).")
    full_name: str = Field(min_length=1, max_length=200, description="The new user's display name.")
    role: Role = Field(description="Role to grant the user within the target organization.")
    # Required when the caller is SUPER_ADMIN (which org to create the user in).
    # Ignored/overridden for org-scoped callers, who may only create within their own org.
    organization_id: str | None = Field(
        default=None,
        description="Organization to create the user in. Required when the caller is a Super "
        "Admin; ignored for org-scoped callers, who can only create users in their own organization.",
    )


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200, description="New display name, if changing it.")
    role: Role | None = Field(default=None, description="New role within the organization, if changing it.")
    status: UserStatus | None = Field(default=None, description="New lifecycle status, if changing it (e.g. to disable the user).")
    password: str | None = Field(default=None, min_length=8, description="New password (min. 8 characters), if resetting it.")


class UserSelfUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200, description="New display name, if changing it.")
    password: str | None = Field(default=None, min_length=8, description="New password (min. 8 characters), if changing it. Requires `current_password`.")
    current_password: str | None = Field(default=None, description="The caller's current password, required to set a new `password`.")


class UserOut(BaseModel):
    id: str = Field(description="The user's id.")
    # organization_id/role reflect the membership in scope for this response
    # (the caller's current org, or the org just acted on) — a user with no
    # resolvable single-org context (e.g. a Super Admin's cross-org listing)
    # gets both as None. See users_service.users.service.
    organization_id: str | None = Field(
        description="The organization this response's membership/role is scoped to. `null` for a "
        "Super Admin or a listing with no single resolvable organization context."
    )
    email: EmailStr = Field(description="The user's email address.")
    full_name: str = Field(description="The user's display name.")
    role: Role | None = Field(description="The user's role within `organization_id`. `null` when `organization_id` is null.")
    is_super_admin: bool = Field(description="Whether this user has platform-wide Super Admin access, bypassing per-organization roles.")
    status: UserStatus = Field(description="Current lifecycle status.")
    must_change_password: bool = Field(description="Whether the user is required to set a new password. Cleared automatically the next time the user changes their own password via `PATCH /users/me`.")
    created_by: str | None = Field(default=None, description="Id of the user who created this account, if known.")
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = Field(description="When the user last logged in successfully; `null` if never.")
