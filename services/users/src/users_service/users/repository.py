"""User data access.

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
from common.enums import Role

from users_service.enums import UserStatus
from users_service.users.model import User


async def create_user(
    email: str,
    hashed_password: str,
    full_name: str,
    role: Role,
    organization_id: PydanticObjectId | None,
    created_by: PydanticObjectId | None,
    status: UserStatus = UserStatus.ACTIVE,
) -> User:
    user = User(
        organization_id=organization_id,
        email=email,
        hashed_password=hashed_password,
        full_name=full_name,
        role=role,
        status=status,
        created_by=created_by,
    )
    await user.insert()
    return user


async def get_by_email(email: str) -> User | None:
    """Email is globally unique, so login can resolve a user without org context."""
    return await User.find_one(User.email == email)


async def get_by_id_scoped(user_id: PydanticObjectId, organization_id: PydanticObjectId) -> User | None:
    return await User.find_one(User.id == user_id, User.organization_id == organization_id)


async def get_by_id_global(user_id: PydanticObjectId) -> User | None:
    return await User.get(user_id)


def _search_condition(search: str) -> Or:
    pattern = re.escape(search)
    return Or(RegEx(User.full_name, pattern, "i"), RegEx(User.email, pattern, "i"))


async def list_by_org(
    organization_id: PydanticObjectId,
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
    status: UserStatus | None = None,
) -> list[User]:
    conditions = [User.organization_id == organization_id]
    if status is not None:
        conditions.append(User.status == status)
    if search:
        conditions.append(_search_condition(search))
    return await User.find(*conditions).skip(skip).limit(limit).to_list()


async def list_all(
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
    status: UserStatus | None = None,
) -> list[User]:
    conditions = []
    if status is not None:
        conditions.append(User.status == status)
    if search:
        conditions.append(_search_condition(search))
    return await User.find(*conditions).skip(skip).limit(limit).to_list()


async def update_user(
    user: User,
    full_name: str | None = None,
    role: Role | None = None,
    status: UserStatus | None = None,
    hashed_password: str | None = None,
    must_change_password: bool | None = None,
) -> User:
    if full_name is not None:
        user.full_name = full_name
    if role is not None:
        user.role = role
    if status is not None:
        user.status = status
    if hashed_password is not None:
        user.hashed_password = hashed_password
    if must_change_password is not None:
        user.must_change_password = must_change_password
    user.updated_at = datetime.now(timezone.utc)
    await user.save()
    return user


async def record_login(user: User) -> None:
    user.last_login_at = datetime.now(timezone.utc)
    await user.save()
