from beanie import PydanticObjectId
from common.enums import Role
from common.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError, UnauthorizedError

from users_service.auth import repository as refresh_token_repo
from users_service.core.deps import AuthContext
from users_service.core.security import hash_password, verify_password
from users_service.enums import UserStatus
from users_service.memberships import repository as membership_repo
from users_service.memberships.model import OrganizationMembership
from users_service.organizations import repository as organization_repo
from users_service.users import repository as user_repo
from users_service.users.model import User

ORG_ASSIGNABLE_ROLES = {Role.ADMIN, Role.DEVELOPER, Role.QA}


async def create_user(
    auth: AuthContext,
    email: str,
    password: str,
    full_name: str,
    role: Role,
    organization_id: str | None,
) -> tuple[User, OrganizationMembership]:
    if role not in ORG_ASSIGNABLE_ROLES:
        raise BadRequestError("role must be one of ADMIN, DEVELOPER, QA", {"field": "role"})

    if auth.is_super_admin:
        if not organization_id:
            raise BadRequestError("organization_id is required", {"field": "organization_id"})
        try:
            target_org_id = PydanticObjectId(organization_id)
        except Exception:
            raise BadRequestError("organization_id is not a valid id", {"field": "organization_id"})
        if await organization_repo.get_by_id(target_org_id) is None:
            raise NotFoundError("Organization not found")
    else:
        # Admin: always the caller's own org, regardless of what the client sent.
        target_org_id = auth.organization_id

    if await user_repo.get_by_email(email) is not None:
        raise ConflictError("A user with this email already exists", {"field": "email"})

    user = await user_repo.create_user(
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        created_by=auth.user_id,
        status=UserStatus.ACTIVE,
    )
    membership = await membership_repo.create(user.id, target_org_id, role, created_by=auth.user_id)
    return user, membership


async def list_users(
    auth: AuthContext,
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
    status: UserStatus | None = None,
) -> list[tuple[User, OrganizationMembership | None]]:
    if auth.is_super_admin:
        # Cross-org: no single "current org" to resolve a membership against.
        return [(user, None) for user in await user_repo.list_all(skip=skip, limit=limit, search=search, status=status)]
    if auth.role == Role.QA:
        raise ForbiddenError("You do not have permission to list users")
    return await user_repo.list_by_org(auth.organization_id, skip=skip, limit=limit, search=search, status=status)


async def get_user(auth: AuthContext, user_id: PydanticObjectId) -> tuple[User, OrganizationMembership | None]:
    if auth.role == Role.QA:
        raise ForbiddenError("You do not have permission to view other users")

    if auth.is_super_admin:
        user = await user_repo.get_by_id_global(user_id)
        if user is None:
            raise NotFoundError("User not found")
        return user, None

    found = await user_repo.get_by_id_scoped(user_id, auth.organization_id)
    if found is None:
        raise NotFoundError("User not found")
    return found


async def update_user(
    auth: AuthContext,
    user_id: PydanticObjectId,
    full_name: str | None,
    role: Role | None,
    status: UserStatus | None,
    password: str | None,
) -> tuple[User, OrganizationMembership | None]:
    if role is not None and role not in ORG_ASSIGNABLE_ROLES:
        raise BadRequestError("role must be one of ADMIN, DEVELOPER, QA", {"field": "role"})

    if auth.is_super_admin:
        target = await user_repo.get_by_id_global(user_id)
        if target is None:
            raise NotFoundError("User not found")
        membership: OrganizationMembership | None = None
        if role is not None:
            # No org context to scope the role change to for a Super Admin
            # target picked cross-org — only unambiguous when the user has
            # exactly one membership; otherwise use the org-scoped
            # membership endpoint (PATCH /organizations/{org_id}/members/{user_id}).
            memberships = await membership_repo.list_for_user(user_id)
            if len(memberships) != 1:
                raise BadRequestError(
                    "This user belongs to zero or multiple organizations; update their role via "
                    "PATCH /organizations/{organization_id}/members/{user_id} instead",
                    {"field": "role"},
                )
            membership = await membership_repo.update_role(memberships[0], role)
    else:
        found = await user_repo.get_by_id_scoped(user_id, auth.organization_id)
        if found is None:
            raise NotFoundError("User not found")
        target, membership = found
        if role is not None:
            membership = await membership_repo.update_role(membership, role)

    hashed_password = hash_password(password) if password else None
    updated = await user_repo.update_user(target, full_name=full_name, status=status, hashed_password=hashed_password)
    if password:
        await refresh_token_repo.revoke_all_for_user(updated.id)
    return updated, membership


async def disable_user(auth: AuthContext, user_id: PydanticObjectId) -> tuple[User, OrganizationMembership | None]:
    if auth.is_super_admin:
        target = await user_repo.get_by_id_global(user_id)
        if target is None:
            raise NotFoundError("User not found")
        membership: OrganizationMembership | None = None
    else:
        found = await user_repo.get_by_id_scoped(user_id, auth.organization_id)
        if found is None:
            raise NotFoundError("User not found")
        target, membership = found

    updated = await user_repo.update_user(target, status=UserStatus.DISABLED)
    await refresh_token_repo.revoke_all_for_user(updated.id)
    return updated, membership


async def update_self(
    auth: AuthContext, full_name: str | None, password: str | None, current_password: str | None
) -> User:
    user = auth.user

    if password:
        if not current_password or not verify_password(current_password, user.hashed_password):
            raise UnauthorizedError("Current password is incorrect")

    hashed_password = hash_password(password) if password else None
    updated = await user_repo.update_user(
        user, full_name=full_name, hashed_password=hashed_password, must_change_password=False if password else None
    )
    if password:
        await refresh_token_repo.revoke_all_for_user(updated.id)
    return updated
