from dataclasses import dataclass

import jwt
from beanie import PydanticObjectId
from common.enums import Role
from common.errors import ForbiddenError, UnauthorizedError
from common.log_utils import setup_logger
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from users_service.core.security import ACCESS_TOKEN_TYPE, decode_own_token
from users_service.enums import UserStatus
from users_service.memberships import repository as membership_repo
from users_service.organizations.model import Organization
from users_service.permissions.service import PermissionService
from users_service.users.model import User

logger = setup_logger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)
_permission_service = PermissionService()


@dataclass(frozen=True)
class AuthContext:
    """`organization_id`/`role` are resolved once per request in
    get_current_auth — never trusted from a stale JWT claim, and never a
    plain property of `user` any more, since role is per-organization
    membership, not a field on User. `organization_id` is the org this
    *session* (access token) is scoped to (None only for a Super Admin).
    """

    user: User
    organization_id: PydanticObjectId | None
    role: Role

    @property
    def user_id(self) -> PydanticObjectId:
        return self.user.id

    @property
    def is_super_admin(self) -> bool:
        return self.user.is_super_admin


async def get_current_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthContext:
    if credentials is None:
        raise UnauthorizedError("Missing bearer token")

    try:
        payload = decode_own_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Access token has expired")
    except jwt.InvalidTokenError:
        raise UnauthorizedError("Invalid access token")

    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise UnauthorizedError("Invalid token type")

    try:
        user_id = PydanticObjectId(payload["sub"])
    except Exception:
        raise UnauthorizedError("Invalid token subject")

    # Re-read the user on every request (never trust stale JWT claims for
    # status): this makes disable-user take effect immediately instead of
    # waiting out the access token's lifetime.
    user = await User.get(user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise UnauthorizedError("User is not active")

    if user.is_super_admin:
        # A Super Admin has no membership, but may have switched into an
        # organization (see /auth/switch-organization): keep that context.
        # Role stays SUPER_ADMIN. A claim for a since-deleted org is ignored.
        return AuthContext(
            user=user,
            organization_id=await resolve_super_admin_org(payload.get("organization_id")),
            role=Role.SUPER_ADMIN,
        )

    organization_id_claim = payload.get("organization_id")
    if not organization_id_claim:
        raise UnauthorizedError("Access token has no organization context")
    try:
        organization_id = PydanticObjectId(organization_id_claim)
    except Exception:
        raise UnauthorizedError("Invalid organization context")

    # Role is never trusted from the token — always resolved fresh from
    # membership, so a role change (or removal from the org) takes effect
    # on the very next request, not when the token happens to expire.
    membership = await membership_repo.get(user_id, organization_id)
    if membership is None:
        raise UnauthorizedError("You no longer have access to this organization")

    return AuthContext(user=user, organization_id=organization_id, role=membership.role)


async def resolve_super_admin_org(claim: str | None) -> PydanticObjectId | None:
    if not claim:
        return None
    try:
        org = await Organization.get(PydanticObjectId(claim))
    except Exception:
        return None
    return org.id if org else None


def require_role(*allowed_roles: Role):
    async def _checker(auth: AuthContext = Depends(get_current_auth)) -> AuthContext:
        if auth.role not in allowed_roles:
            raise ForbiddenError("You do not have permission to perform this action")
        return auth

    return _checker


def require_permission(permission: str):
    """Like require_role, but checks a fine-grained permission key against the
    caller's role via RolePermissionMapping (see users_service.permissions),
    instead of hardcoding a role list at each call site.
    """

    async def _checker(auth: AuthContext = Depends(get_current_auth)) -> AuthContext:
        granted = await _permission_service.get_role_permissions(auth.role)
        if not _permission_service.has_permission(granted, permission):
            logger.warning(
                "Permission denied: role=%s required=%s granted=%s", auth.role, permission, granted
            )
            raise ForbiddenError("You do not have permission to perform this action")
        return auth

    return _checker
