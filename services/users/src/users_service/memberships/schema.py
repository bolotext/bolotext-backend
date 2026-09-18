from datetime import datetime

from common.enums import Role
from pydantic import BaseModel


class MembershipCreate(BaseModel):
    user_id: str
    role: Role


class MembershipUpdate(BaseModel):
    role: Role


class MembershipOut(BaseModel):
    user_id: str
    organization_id: str
    email: str
    full_name: str
    role: Role
    created_at: datetime


class MyOrganizationOut(BaseModel):
    organization_id: str
    name: str
    slug: str
    role: Role
