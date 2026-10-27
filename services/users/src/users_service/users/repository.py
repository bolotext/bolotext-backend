"""User identity data access. Role now lives on OrganizationMembership, not
User — every function here that returns a role does so by joining against
`users_service.memberships`, keyed by whichever organization is in scope for
the caller (see users_service.users.service).

Every read/list function that is meant to be reachable by an org-scoped caller
(Admin/Developer/QA) takes `organization_id` as a required, non-optional
argument and always includes it in the Mongo filter. Functions suffixed
`_global` skip that filter and must only ever be called from Super Admin code
paths in users/service.py.
"""

import re
from datetime import datetime, timezone

from beanie import PydanticObjectId
from beanie.operators import Or, RegEx

from users_service.enums import UserStatus
from users_service.memberships import repository as membership_repo
from users_service.memberships.model import OrganizationMembership
from users_service.users.model import User


async def create_user(
    email: str,
    full_name: str,
    created_by: PydanticObjectId | None,
    status: UserStatus = UserStatus.ACTIVE,
    is_super_admin: bool = False,
) -> User:
    user = User(
        email=email,
        full_name=full_name,
        is_super_admin=is_super_admin,
        status=status,
        created_by=created_by,
    )
    await user.insert()
    return user


async def get_by_email(email: str) -> User | None:
    """Email is globally unique, so login can resolve a user without org context."""
    return await User.find_one(User.email == email)


async def get_by_id_scoped(
    user_id: PydanticObjectId, organization_id: PydanticObjectId
) -> tuple[User, OrganizationMembership] | None:
    """Confirms `user_id` has a membership in `organization_id` before
    returning it, and hands back that membership (role + org id) along with
    the user — there's no other way to answer "what role does this user
    have here" now that role isn't a plain field on User.
    """
    membership = await membership_repo.get(user_id, organization_id)
    if membership is None:
        return None
    user = await User.get(user_id)
    if user is None:
        return None
    return user, membership


async def get_by_id_global(user_id: PydanticObjectId) -> User | None:
    return await User.get(user_id)


async def get_many_by_ids(user_ids: list[PydanticObjectId]) -> list[User]:
    if not user_ids:
        return []
    return await User.find({"_id": {"$in": user_ids}}).to_list()


def _search_condition(search: str) -> Or:
    pattern = re.escape(search)
    return Or(RegEx(User.full_name, pattern, "i"), RegEx(User.email, pattern, "i"))


async def list_by_org(
    organization_id: PydanticObjectId,
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
    status: UserStatus | None = None,
) -> list[tuple[User, OrganizationMembership]]:
    """Every member of `organization_id`, paired with their membership there.
    Paging/search/status are applied to the joined (user, membership) pairs,
    not just the membership rows, since `search` filters on User fields.
    """
    memberships = await membership_repo.list_for_org(organization_id, skip=0, limit=0) or []
    membership_by_user_id = {m.user_id: m for m in memberships}
    if not membership_by_user_id:
        return []

    conditions = [{"_id": {"$in": list(membership_by_user_id)}}]
    if status is not None:
        conditions.append(User.status == status)
    if search:
        conditions.append(_search_condition(search))
    users = await User.find(*conditions).skip(skip).limit(limit).to_list()
    return [(user, membership_by_user_id[user.id]) for user in users]


async def list_all(
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
    status: UserStatus | None = None,
) -> list[User]:
    """Cross-org listing (Super Admin only). There's no single "current org"
    to resolve a role against here, so callers get identities only — see
    users_service.users.service.list_users's SUPER_ADMIN branch.
    """
    conditions = []
    if status is not None:
        conditions.append(User.status == status)
    if search:
        conditions.append(_search_condition(search))
    return await User.find(*conditions).skip(skip).limit(limit).to_list()


async def update_user(
    user: User,
    full_name: str | None = None,
    status: UserStatus | None = None,
) -> User:
    if full_name is not None:
        user.full_name = full_name
    if status is not None:
        user.status = status
    user.updated_at = datetime.now(timezone.utc)
    await user.save()
    return user


async def record_login(user: User) -> None:
    user.last_login_at = datetime.now(timezone.utc)
    await user.save()
