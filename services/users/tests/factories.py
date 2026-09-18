from beanie import PydanticObjectId
from common.enums import Role

from users_service.core.security import create_access_token, hash_password
from users_service.enums import UserStatus
from users_service.memberships.model import OrganizationMembership
from users_service.organizations.model import Organization
from users_service.users.model import User

# Tests build a User via make_user(organization_id, role, ...) exactly as
# before multi-org membership existed — the org/role pair is stashed here
# (keyed by user id) instead of living on the User document, so auth_header
# doesn't need every call site updated to pass organization_id separately.
_MEMBERSHIP_BY_USER_ID: dict[PydanticObjectId, PydanticObjectId | None] = {}


async def make_org(name: str, slug: str) -> Organization:
    org = Organization(name=name, slug=slug, created_by=PydanticObjectId())
    await org.insert()
    return org


async def make_user(
    organization_id: PydanticObjectId | None,
    role: Role,
    email: str,
    password: str = "password123",
    status: UserStatus = UserStatus.ACTIVE,
) -> User:
    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=email,
        is_super_admin=role == Role.SUPER_ADMIN,
        status=status,
    )
    await user.insert()

    if role != Role.SUPER_ADMIN:
        assert organization_id is not None, "organization_id is required for a non-SUPER_ADMIN test user"
        await OrganizationMembership(user_id=user.id, organization_id=organization_id, role=role).insert()

    _MEMBERSHIP_BY_USER_ID[user.id] = organization_id if role != Role.SUPER_ADMIN else None
    return user


def auth_header(user: User, organization_id: PydanticObjectId | None = None) -> dict:
    """`organization_id` only needs to be passed explicitly for a user with
    more than one membership (make_user only ever creates one); otherwise
    it's resolved from the membership make_user created.
    """
    org_id = organization_id if organization_id is not None else _MEMBERSHIP_BY_USER_ID.get(user.id)
    token = create_access_token(str(user.id), str(org_id) if org_id else None)
    return {"Authorization": f"Bearer {token}"}


def data(resp) -> dict:
    """Unwrap the {status, code, message, data} success envelope."""
    return resp.json()["data"]


def code(resp) -> int:
    """The envelope's real status code. The HTTP transport status is always
    200 — see common.errors.register_exception_handlers.
    """
    return resp.json()["code"]


def error_type(resp) -> str:
    """Unwrap the {status, code, message, errors: {type, ...}} error envelope."""
    return resp.json()["errors"]["type"]
