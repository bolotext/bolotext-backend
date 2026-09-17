from common.enums import Role
from common.log_utils import setup_logger

from users_service.core.config import get_settings
from users_service.core.security import hash_password
from users_service.enums import UserStatus
from users_service.permissions.repository import PermissionRepository
from users_service.roles.repository import RoleRepository
from users_service.users.model import User

logger = setup_logger(__name__)

ROLE_DESCRIPTIONS: dict[Role, str] = {
    Role.SUPER_ADMIN: "Platform-level administrator, not scoped to any organization.",
    Role.ADMIN: "Organization owner. Manages users within their own organization.",
    Role.DEVELOPER: "Organization member with technical/API access and read-only user listing.",
    Role.QA: "Organization member with read-mostly access, scoped to their own profile.",
}

# Permission keys granted per role. "*" grants everything; "<module>.*" grants
# every action in that module. Kept in sync with the require_permission(...)
# calls in each module's router.
ROLE_PERMISSIONS: dict[Role, list[str]] = {
    Role.SUPER_ADMIN: ["*"],
    Role.ADMIN: ["user.*"],
    Role.DEVELOPER: ["user.view"],
    Role.QA: [],
}

PERMISSION_DESCRIPTIONS: dict[str, str] = {
    "user.create": "Create a user.",
    "user.view": "View user profiles and listings.",
    "user.update": "Update a user's profile, role, or status.",
    "user.delete": "Disable a user.",
    "user.*": "All user permissions.",
    "organization.create": "Create an organization.",
    "organization.view": "View organizations.",
    "organization.update": "Update an organization.",
    "organization.*": "All organization permissions.",
    "*": "All permissions (platform-level).",
}


async def seed_roles() -> None:
    role_repo = RoleRepository()
    for role, description in ROLE_DESCRIPTIONS.items():
        existing = await role_repo.get_by_name(role)
        if existing is None:
            await role_repo.create(role, description)
            logger.info("Seeded role %s", role)


async def seed_permissions() -> None:
    """Idempotent: upserts each permission and its role mapping. Requires
    seed_roles() to have already run, since mappings link to a role's id.
    """
    role_repo = RoleRepository()
    permission_repo = PermissionRepository()

    for role, permission_keys in ROLE_PERMISSIONS.items():
        role_doc = await role_repo.get_by_name(role)
        if role_doc is None:
            logger.warning("Role %s not seeded yet, skipping its permission mappings", role)
            continue

        for key in permission_keys:
            permission = await permission_repo.get_by_key(key)
            if permission is None:
                permission = await permission_repo.create(
                    key=key, module=key.split(".")[0], description=PERMISSION_DESCRIPTIONS.get(key, key)
                )
                logger.info("Seeded permission %s", key)

            existing_mapping = await permission_repo.find_mapping(role_doc.id, permission.id)
            if existing_mapping is None:
                await permission_repo.create_mapping(role_doc.id, permission.id)
                logger.info("Seeded role-permission mapping: %s -> %s", role, key)


async def seed_bootstrap_super_admin() -> None:
    settings = get_settings()
    if not settings.bootstrap_super_admin_email or not settings.bootstrap_super_admin_password:
        logger.info("No bootstrap super admin configured, skipping.")
        return

    existing = await User.find_one(
        User.organization_id == None,  # noqa: E711 - Beanie query operator requires `==`
        User.email == settings.bootstrap_super_admin_email,
    )
    if existing is not None:
        logger.info("Bootstrap super admin already exists, skipping.")
        return

    await User(
        organization_id=None,
        email=settings.bootstrap_super_admin_email,
        hashed_password=hash_password(settings.bootstrap_super_admin_password),
        full_name=settings.bootstrap_super_admin_name,
        role=Role.SUPER_ADMIN,
        status=UserStatus.ACTIVE,
        created_by=None,
    ).insert()
    logger.info("Bootstrap super admin created: %s", settings.bootstrap_super_admin_email)


async def seed_all() -> None:
    """Idempotent: safe to run on every startup and via a manual `python main.py seed`."""
    await seed_roles()
    await seed_permissions()
    await seed_bootstrap_super_admin()
