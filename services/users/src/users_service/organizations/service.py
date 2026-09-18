from beanie import PydanticObjectId
from common.enums import Role
from common.errors import ConflictError, NotFoundError

from users_service.core.security import hash_password
from users_service.enums import OrganizationStatus, UserStatus
from users_service.memberships import repository as membership_repo
from users_service.organizations.model import Organization
from users_service.organizations import repository as organization_repo
from users_service.users import repository as user_repo
from users_service.users.model import User


async def create_organization(
    name: str,
    slug: str,
    created_by: PydanticObjectId,
    admin_email: str | None = None,
    admin_password: str | None = None,
    admin_full_name: str | None = None,
) -> tuple[Organization, User | None]:
    if await organization_repo.get_by_slug(slug) is not None:
        raise ConflictError("An organization with this slug already exists", {"field": "slug"})

    admin_user: User | None = None
    if admin_email:
        if await user_repo.get_by_email(admin_email) is not None:
            raise ConflictError("A user with this email already exists", {"field": "admin_email"})
        if not admin_password:
            raise ConflictError("admin_password is required when admin_email is provided", {"field": "admin_password"})

    org = await organization_repo.create_organization(name=name, slug=slug, created_by=created_by)

    if admin_email:
        admin_user = await user_repo.create_user(
            email=admin_email,
            hashed_password=hash_password(admin_password),
            full_name=admin_full_name or admin_email,
            created_by=created_by,
            status=UserStatus.ACTIVE,
        )
        await membership_repo.create(admin_user.id, org.id, Role.ADMIN, created_by=created_by)

    return org, admin_user


async def get_organization(organization_id: PydanticObjectId) -> Organization:
    org = await organization_repo.get_by_id(organization_id)
    if org is None:
        raise NotFoundError("Organization not found")
    return org


async def list_organizations(
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
    status: OrganizationStatus | None = None,
) -> list[Organization]:
    return await organization_repo.list_organizations(skip=skip, limit=limit, search=search, status=status)


async def update_organization(
    organization_id: PydanticObjectId, name: str | None, status: OrganizationStatus | None
) -> Organization:
    org = await get_organization(organization_id)
    return await organization_repo.update_organization(org, name=name, status=status)
