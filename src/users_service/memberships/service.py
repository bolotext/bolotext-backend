from beanie import PydanticObjectId
from common.enums import Role
from common.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError

from users_service.core.deps import AuthContext
from users_service.memberships import repository as membership_repo
from users_service.memberships.model import OrganizationMembership
from users_service.organizations import repository as organization_repo
from users_service.organizations.model import Organization
from users_service.users import repository as user_repo
from users_service.users.model import User
from users_service.users.service import ORG_ASSIGNABLE_ROLES


def _assert_can_manage_org(auth: AuthContext, organization_id: PydanticObjectId) -> None:
    if auth.is_super_admin:
        return
    if auth.organization_id != organization_id:
        raise ForbiddenError("You can only manage members of your own organization")


async def add_membership(
    auth: AuthContext, organization_id: PydanticObjectId, user_id: PydanticObjectId, role: Role
) -> tuple[User, OrganizationMembership]:
    if role not in ORG_ASSIGNABLE_ROLES:
        raise BadRequestError("role must be one of ADMIN, DEVELOPER, QA", {"field": "role"})
    if auth.is_super_admin:
        if await organization_repo.get_by_id(organization_id) is None:
            raise NotFoundError("Organization not found")
    else:
        _assert_can_manage_org(auth, organization_id)

    target_user = await user_repo.get_by_id_global(user_id)
    if target_user is None:
        raise NotFoundError("User not found")

    if await membership_repo.get(user_id, organization_id) is not None:
        raise ConflictError("User is already a member of this organization")

    membership = await membership_repo.create(user_id, organization_id, role, created_by=auth.user_id)
    return target_user, membership


async def list_members(
    auth: AuthContext, organization_id: PydanticObjectId, skip: int = 0, limit: int = 50
) -> list[tuple[User, OrganizationMembership]]:
    _assert_can_manage_org(auth, organization_id)
    memberships = await membership_repo.list_for_org(organization_id, skip=skip, limit=limit)
    users = await user_repo.get_many_by_ids([m.user_id for m in memberships])
    users_by_id = {u.id: u for u in users}
    return [(users_by_id[m.user_id], m) for m in memberships if m.user_id in users_by_id]


async def update_membership_role(
    auth: AuthContext, organization_id: PydanticObjectId, user_id: PydanticObjectId, role: Role
) -> tuple[User, OrganizationMembership]:
    if role not in ORG_ASSIGNABLE_ROLES:
        raise BadRequestError("role must be one of ADMIN, DEVELOPER, QA", {"field": "role"})
    _assert_can_manage_org(auth, organization_id)

    membership = await membership_repo.get(user_id, organization_id)
    if membership is None:
        raise NotFoundError("Membership not found")
    membership = await membership_repo.update_role(membership, role)

    target_user = await user_repo.get_by_id_global(user_id)
    return target_user, membership


async def remove_membership(auth: AuthContext, organization_id: PydanticObjectId, user_id: PydanticObjectId) -> None:
    _assert_can_manage_org(auth, organization_id)

    membership = await membership_repo.get(user_id, organization_id)
    if membership is None:
        raise NotFoundError("Membership not found")
    await membership_repo.delete(membership)


async def list_my_memberships(
    auth: AuthContext, page: int = 1, limit: int = 10
) -> tuple[list[tuple[Organization, Role]], int]:
    """Returns (this page of (org, role) pairs, total count). A Super Admin
    has no memberships and can enter any organization, so they get every
    organization (role SUPER_ADMIN) instead."""
    skip = (page - 1) * limit
    if auth.is_super_admin:
        total = await organization_repo.count_organizations()
        orgs = await organization_repo.list_organizations(skip=skip, limit=limit)
        return [(o, Role.SUPER_ADMIN) for o in orgs], total

    memberships = await membership_repo.list_for_user(auth.user_id)
    orgs = await organization_repo.get_many_by_ids([m.organization_id for m in memberships])
    orgs_by_id = {o.id: o for o in orgs}
    pairs = [(orgs_by_id[m.organization_id], m.role) for m in memberships if m.organization_id in orgs_by_id]
    pairs.sort(key=lambda p: (p[0].name, str(p[0].id)))
    return pairs[skip : skip + limit], len(pairs)
