from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from users_service.enums import OrganizationStatus


class OrganizationCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Example Bank",
                "slug": "example-bank",
                "admin_email": "admin@example-bank.example",
                "admin_full_name": "Jane Admin",
            }
        }
    )

    name: str = Field(min_length=1, max_length=200, description="Display name of the new organization.")
    slug: str = Field(min_length=1, max_length=200, description="URL/identifier-safe unique slug for the organization.")

    # Optional bootstrap of the first Admin user for this org
    admin_email: EmailStr | None = Field(
        default=None, description="Email for the org's first Admin user, if bootstrapping one now."
    )
    admin_full_name: str | None = Field(default=None, description="Full name for the bootstrapped Admin user.")


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200, description="New display name, if changing it.")
    status: OrganizationStatus | None = Field(default=None, description="New lifecycle status, if changing it.")


class OrganizationOut(BaseModel):
    id: str = Field(description="The organization's id.")
    name: str = Field(description="The organization's display name.")
    slug: str = Field(description="The organization's unique slug.")
    status: OrganizationStatus = Field(description="Current lifecycle status.")
    created_by: str = Field(description="Id of the user who created this organization.")
    created_at: datetime
    updated_at: datetime


class OrganizationCreateResponse(BaseModel):
    organization: OrganizationOut
    admin_user_id: str | None = Field(
        default=None, description="Id of the bootstrapped Admin user, if `admin_email` was supplied."
    )
