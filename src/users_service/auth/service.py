import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

import jwt
from beanie import PydanticObjectId
from common.errors import BadRequestError, ForbiddenError, NotFoundError, UnauthorizedError
from common.jwt import REFRESH_TOKEN_TYPE
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from users_service.auth import repository as refresh_token_repo
from users_service.auth.schema import OrganizationChoice
from users_service.core.config import get_settings
from users_service.core.security import (
    create_access_token,
    create_refresh_token,
    decode_own_token,
    hash_refresh_token,
)
from users_service.core.time import ensure_aware_utc
from users_service.enums import UserStatus
from users_service.memberships import repository as membership_repo
from users_service.memberships.model import OrganizationMembership
from users_service.organizations import repository as organization_repo
from users_service.users import repository as user_repo
from users_service.users.model import User


@dataclass(frozen=True)
class LoginResult:
    requires_selection: bool
    organizations: list[OrganizationChoice] | None = None
    user: User | None = None
    access_token: str | None = None
    refresh_token: str | None = None


async def _issue_session(user: User, organization_id: PydanticObjectId | None) -> tuple[str, str]:
    access_token = create_access_token(str(user.id), str(organization_id) if organization_id else None)
    refresh_token = create_refresh_token(str(user.id))
    payload = decode_own_token(refresh_token)
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    await refresh_token_repo.create_refresh_token(
        user.id, hash_refresh_token(refresh_token), expires_at, organization_id=organization_id
    )
    return access_token, refresh_token


async def _resolve_organization_choices(memberships: list[OrganizationMembership]) -> list[OrganizationChoice]:
    orgs = await organization_repo.get_many_by_ids([m.organization_id for m in memberships])
    orgs_by_id = {o.id: o for o in orgs}
    return [
        OrganizationChoice(organization_id=str(m.organization_id), name=orgs_by_id[m.organization_id].name, role=m.role)
        for m in memberships
        if m.organization_id in orgs_by_id
    ]


def _verify_google_token(token: str) -> str:
    """Validates a Google ID token (signature, expiry, audience) and returns
    the verified email address it was issued for.
    """
    client_id = get_settings().google_client_id
    if not client_id:
        raise UnauthorizedError("Google sign-in is not configured")
    try:
        claims = google_id_token.verify_oauth2_token(token, google_requests.Request(), client_id)
    except ValueError:
        raise UnauthorizedError("Invalid Google credential")
    email = claims.get("email")
    if not email or not claims.get("email_verified"):
        raise UnauthorizedError("Google account email is not verified")
    return email.lower()


async def login(google_credential: str, organization_id: str | None = None) -> LoginResult:
    # Network fetch of Google's signing certs happens inside; keep it off the event loop.
    email = await asyncio.to_thread(_verify_google_token, google_credential)
    user = await user_repo.get_by_email(email)
    if user is None:
        raise UnauthorizedError("No account exists for this Google user")
    if user.status != UserStatus.ACTIVE:
        raise UnauthorizedError("This account is not active")

    target_org_id: PydanticObjectId | None = None

    if not user.is_super_admin:
        memberships = await membership_repo.list_for_user(user.id)
        if not memberships:
            raise UnauthorizedError("This user has no organization access")

        if organization_id:
            try:
                requested_org_id = PydanticObjectId(organization_id)
            except Exception:
                raise BadRequestError("organization_id is not a valid id", {"field": "organization_id"})
            match = next((m for m in memberships if m.organization_id == requested_org_id), None)
            if match is None:
                raise UnauthorizedError("You do not have access to this organization")
            target_org_id = match.organization_id
        elif len(memberships) == 1:
            target_org_id = memberships[0].organization_id
        else:
            # Multi-org user: sign into the last-used org (else the oldest
            # membership); they can switch afterwards via /auth/switch-organization.
            member_org_ids = {m.organization_id for m in memberships}
            last_used = await refresh_token_repo.get_last_used_organization_id(user.id)
            if last_used in member_org_ids:
                target_org_id = last_used
            else:
                target_org_id = min(memberships, key=lambda m: m.created_at).organization_id

    access_token, refresh_token = await _issue_session(user, target_org_id)
    await user_repo.record_login(user)
    return LoginResult(requires_selection=False, user=user, access_token=access_token, refresh_token=refresh_token)


async def refresh_access_token(refresh_token: str) -> str:
    try:
        payload = decode_own_token(refresh_token)
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Refresh token has expired")
    except jwt.InvalidTokenError:
        raise UnauthorizedError("Invalid refresh token")

    if payload.get("type") != REFRESH_TOKEN_TYPE:
        raise UnauthorizedError("Invalid token type")

    record = await refresh_token_repo.get_valid_by_hash(hash_refresh_token(refresh_token))
    if record is None:
        raise UnauthorizedError("Refresh token has been revoked or does not exist")
    if ensure_aware_utc(record.expires_at) < datetime.now(timezone.utc):
        raise UnauthorizedError("Refresh token has expired")

    user = await user_repo.get_by_id_global(record.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise UnauthorizedError("User is not active")

    # Re-mint for the same org this refresh token was pinned to at login/
    # switch time — a since-revoked membership isn't re-checked here; it'll
    # simply fail the next time get_current_auth/introspect resolves a role
    # for it, same "always re-check at the point of use" approach as the
    # rest of this module.
    return create_access_token(str(user.id), str(record.organization_id) if record.organization_id else None)


async def switch_organization(user: User, organization_id: str) -> tuple[str, str]:
    try:
        target_org_id = PydanticObjectId(organization_id)
    except Exception:
        raise BadRequestError("organization_id is not a valid id", {"field": "organization_id"})

    if user.is_super_admin:
        if await organization_repo.get_by_id(target_org_id) is None:
            raise NotFoundError("Organization not found")
    else:
        if await membership_repo.get(user.id, target_org_id) is None:
            raise ForbiddenError("You do not have access to this organization")

    return await _issue_session(user, target_org_id)


async def logout(refresh_token: str) -> None:
    try:
        decode_own_token(refresh_token)
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Refresh token has expired")
    except jwt.InvalidTokenError:
        raise UnauthorizedError("Invalid refresh token")

    record = await refresh_token_repo.get_valid_by_hash(hash_refresh_token(refresh_token))
    if record is None:
        raise UnauthorizedError("Refresh token has been revoked or does not exist")
    await refresh_token_repo.revoke(record)
