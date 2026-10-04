from datetime import datetime

from common.enums import Role
from pydantic import BaseModel, Field


class MembershipCreate(BaseModel):
    user_id: str = Field(description="Id of an existing user to add to the organization.")
    role: Role = Field(description="Role to grant the user within this organization.")


class MembershipUpdate(BaseModel):
    role: Role = Field(description="New role to grant the user within this organization.")


class MembershipOut(BaseModel):
    user_id: str = Field(description="The member's user id.")
    organization_id: str = Field(description="The organization this membership belongs to.")
    email: str = Field(description="The member's email address.")
    full_name: str = Field(description="The member's full name.")
    role: Role = Field(description="The member's role within this organization.")
    created_at: datetime = Field(description="When the membership was created.")


class MyOrganizationOut(BaseModel):
    organization_id: str = Field(description="The organization's id.")
    name: str = Field(description="The organization's display name.")
    slug: str = Field(description="The organization's unique slug.")
    role: Role = Field(description="The caller's role within this organization.")
