import re
from datetime import datetime, timezone

from beanie import PydanticObjectId
from beanie.operators import Or, RegEx
from common.enums import Feature

from users_service.enums import OrganizationStatus
from users_service.organizations.model import Organization


async def create_organization(
    name: str, slug: str, created_by: PydanticObjectId, features: list[Feature] | None = None
) -> Organization:
    org = Organization(name=name, slug=slug, created_by=created_by)
    if features is not None:
        org.features = features
    await org.insert()
    return org


async def get_by_id(organization_id: PydanticObjectId) -> Organization | None:
    return await Organization.get(organization_id)


async def get_many_by_ids(organization_ids: list[PydanticObjectId]) -> list[Organization]:
    if not organization_ids:
        return []
    return await Organization.find({"_id": {"$in": organization_ids}}).to_list()


async def get_by_slug(slug: str) -> Organization | None:
    return await Organization.find_one(Organization.slug == slug)


def _conditions(search: str | None, status: OrganizationStatus | None) -> list:
    conditions = []
    if status is not None:
        conditions.append(Organization.status == status)
    if search:
        pattern = re.escape(search)
        conditions.append(Or(RegEx(Organization.name, pattern, "i"), RegEx(Organization.slug, pattern, "i")))
    return conditions


async def count_organizations(search: str | None = None, status: OrganizationStatus | None = None) -> int:
    return await Organization.find(*_conditions(search, status)).count()


async def list_organizations(
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
    status: OrganizationStatus | None = None,
) -> list[Organization]:
    # Sort by name (then id) so pages are stable across requests.
    query = Organization.find(*_conditions(search, status)).sort("+name", "+_id")
    return await query.skip(skip).limit(limit).to_list()


async def update_organization(
    org: Organization,
    name: str | None = None,
    status: OrganizationStatus | None = None,
    features: list[Feature] | None = None,
) -> Organization:
    if features is not None:
        org.features = features
    if name is not None:
        org.name = name
    if status is not None:
        org.status = status
    org.updated_at = datetime.now(timezone.utc)
    await org.save()
    return org
