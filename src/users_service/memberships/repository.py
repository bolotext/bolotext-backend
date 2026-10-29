from datetime import datetime, timezone

from beanie import PydanticObjectId
from common.enums import Role

from users_service.memberships.model import OrganizationMembership


async def create(
    user_id: PydanticObjectId, organization_id: PydanticObjectId, role: Role, created_by: PydanticObjectId | None
) -> OrganizationMembership:
    membership = OrganizationMembership(
        user_id=user_id, organization_id=organization_id, role=role, created_by=created_by
    )
    await membership.insert()
    return membership


async def get(user_id: PydanticObjectId, organization_id: PydanticObjectId) -> OrganizationMembership | None:
    return await OrganizationMembership.find_one(
        OrganizationMembership.user_id == user_id, OrganizationMembership.organization_id == organization_id
    )


async def list_for_user(user_id: PydanticObjectId) -> list[OrganizationMembership]:
    return await OrganizationMembership.find(OrganizationMembership.user_id == user_id).to_list()


async def list_for_org(organization_id: PydanticObjectId, skip: int = 0, limit: int = 50) -> list[OrganizationMembership]:
    return (
        await OrganizationMembership.find(OrganizationMembership.organization_id == organization_id)
        .skip(skip)
        .limit(limit)
        .to_list()
    )


async def update_role(membership: OrganizationMembership, role: Role) -> OrganizationMembership:
    membership.role = role
    membership.updated_at = datetime.now(timezone.utc)
    await membership.save()
    return membership


async def delete(membership: OrganizationMembership) -> None:
    await membership.delete()
