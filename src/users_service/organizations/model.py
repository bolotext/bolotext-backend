from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from common.enums import ALL_FEATURES, Feature
from pydantic import Field
from pymongo import IndexModel

from users_service.enums import OrganizationStatus


class Organization(Document):
    name: str
    slug: str
    status: OrganizationStatus = OrganizationStatus.ACTIVE
    # Product areas this organization may use; a Super Admin sets them. Organizations
    # created before this existed have no value stored and keep full access.
    features: list[Feature] = Field(default_factory=lambda: [Feature(f) for f in ALL_FEATURES])
    created_by: PydanticObjectId
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "organizations"
        indexes = [
            IndexModel("slug", unique=True),
        ]
