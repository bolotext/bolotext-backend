from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from users_service.enums import OrganizationStatus


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=200)

    # Optional bootstrap of the first Admin user for this org
    admin_email: EmailStr | None = None
    admin_password: str | None = Field(default=None, min_length=8)
    admin_full_name: str | None = None


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    status: OrganizationStatus | None = None


class OrganizationOut(BaseModel):
    id: str
    name: str
    slug: str
    status: OrganizationStatus
    created_by: str
    created_at: datetime
    updated_at: datetime


class OrganizationCreateResponse(BaseModel):
    organization: OrganizationOut
    admin_user_id: str | None = None
