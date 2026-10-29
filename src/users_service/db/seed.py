from common.enums import Role
from common.log_utils import setup_logger

from users_service.core.config import get_settings
from users_service.enums import UserStatus
from users_service.memberships import repository as membership_repo
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
    Role.ADMIN: ["user.*", "membership.*"],
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
    "membership.create": "Add a user to an organization.",
    "membership.view": "View an organization's members.",
    "membership.update": "Change a member's role within an organization.",
    "membership.delete": "Remove a member from an organization.",
    "membership.*": "All membership permissions.",
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
    if not settings.bootstrap_super_admin_email:
        logger.info("No bootstrap super admin configured, skipping.")
        return

    existing = await User.find_one(User.email == settings.bootstrap_super_admin_email)
    if existing is not None:
        logger.info("Bootstrap super admin already exists, skipping.")
        return

    await User(
        email=settings.bootstrap_super_admin_email,
        full_name=settings.bootstrap_super_admin_name,
        is_super_admin=True,
        status=UserStatus.ACTIVE,
        created_by=None,
    ).insert()
    logger.info("Bootstrap super admin created: %s", settings.bootstrap_super_admin_email)


async def backfill_memberships() -> None:
    """One-time, idempotent migration for pre-multi-org data: `User.role`/
    `User.organization_id` used to live directly on the user document. Any
    document still carrying those legacy fields (raw Mongo, since the Beanie
    `User` model no longer declares them) gets converted to either
    `is_super_admin=True` (legacy SUPER_ADMIN) or a matching
    `OrganizationMembership` row, then has the legacy fields unset. Safe to
    rerun: already-migrated documents have neither field and are skipped.
    """
    collection = User.get_pymongo_collection()
    async for doc in collection.find({"$or": [{"role": {"$exists": True}}, {"organization_id": {"$exists": True}}]}):
        legacy_role = doc.get("role")
        legacy_org_id = doc.get("organization_id")
        user_id = doc["_id"]

        if legacy_role == Role.SUPER_ADMIN.value:
            await collection.update_one(
                {"_id": user_id}, {"$set": {"is_super_admin": True}, "$unset": {"role": "", "organization_id": ""}}
            )
            logger.info("Backfilled legacy SUPER_ADMIN user %s to is_super_admin=True", user_id)
            continue

        if legacy_role and legacy_org_id:
            existing_membership = await membership_repo.get(user_id, legacy_org_id)
            if existing_membership is None:
                await membership_repo.create(user_id, legacy_org_id, Role(legacy_role), created_by=doc.get("created_by"))
                logger.info(
                    "Backfilled membership for user %s: org=%s role=%s", user_id, legacy_org_id, legacy_role
                )

        await collection.update_one({"_id": user_id}, {"$unset": {"role": "", "organization_id": ""}})


async def drop_legacy_password_fields() -> None:
    """One-time, idempotent migration: login is Google-only, so any stored
    `hashed_password` / `must_change_password` is dead credential data. Unset
    it from raw Mongo (the Beanie `User` model no longer declares them).
    """
    result = await User.get_pymongo_collection().update_many(
        {"$or": [{"hashed_password": {"$exists": True}}, {"must_change_password": {"$exists": True}}]},
        {"$unset": {"hashed_password": "", "must_change_password": ""}},
    )
    if result.modified_count:
        logger.info("Removed legacy password fields from %d user(s)", result.modified_count)


async def seed_all() -> None:
    """Idempotent: safe to run on every startup and via a manual `python main.py seed`."""
    await seed_roles()
    await seed_permissions()
    await seed_bootstrap_super_admin()
    await backfill_memberships()
    await drop_legacy_password_fields()
