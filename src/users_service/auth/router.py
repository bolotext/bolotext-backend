import jwt
from beanie import PydanticObjectId
from common.errors import UnauthorizedError
from common.jwt import ACCESS_TOKEN_TYPE, decode_token
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

from users_service.api_tokens import service as api_token_service
from users_service.auth import service as auth_service
from users_service.auth.schema import (
    AccessTokenResponse,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshRequest,
    SwitchOrganizationRequest,
    TokenResponse,
)
from users_service.core.config import get_settings
from users_service.core.deps import AuthContext, get_current_auth, resolve_super_admin_org
from users_service.core.rate_limit import limiter
from users_service.enums import UserStatus
from users_service.memberships import repository as membership_repo
from users_service.organizations import repository as organization_repo
from users_service.users import repository as user_repo

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post(
    "/login",
    response_model=SuccessResponse[LoginResponse],
    summary="Log in with Google and obtain access/refresh tokens",
)
@limiter.limit(settings.login_rate_limit)
async def login(request: Request, payload: LoginRequest) -> dict:
    """Authenticates with a Google ID token and returns a bearer access token
    and refresh token pair for the selected organization. Google is the only
    supported login method; the verified Google email must match an existing
    active account.

    If the account belongs to more than one organization and `organization_id`
    wasn't supplied, no tokens are issued — the response instead carries
    `data.organizations`, the list of organizations to choose from. Retry the
    call with one of those ids set as `organization_id`.

    **Auth:** None required — this is how a caller obtains a token in the
    first place.

    **Errors:**
    - `UNAUTHORIZED` — the Google credential is invalid or unverified, no
      account exists for its email, or the account is not active
      (invited/disabled).
    - `TOO_MANY_REQUESTS` — this endpoint is rate-limited per the configured
      login rate limit; exceeded limits are rejected before credentials are
      even checked.
    """
    result = await auth_service.login(payload.credential, payload.organization_id)
    if result.requires_selection:
        return success_response(
            message="Select an organization to continue",
            data=LoginResponse(organizations=result.organizations),
        )
    return success_response(
        message="Logged in",
        data=LoginResponse(access_token=result.access_token, refresh_token=result.refresh_token),
    )


@router.post(
    "/refresh",
    response_model=SuccessResponse[AccessTokenResponse],
    summary="Exchange a refresh token for a new access token",
)
async def refresh(payload: RefreshRequest) -> dict:
    """Issues a new short-lived access token from a still-valid refresh
    token, without requiring the caller to log in again.

    **Auth:** None required — the refresh token in the body is the
    credential.

    **Errors:**
    - `UNAUTHORIZED` — the refresh token is invalid, expired, or has already
      been revoked (e.g. by `/auth/logout`).
    """
    access_token = await auth_service.refresh_access_token(payload.refresh_token)
    return success_response(message="Access token refreshed", data=AccessTokenResponse(access_token=access_token))


@router.post(
    "/switch-organization",
    response_model=SuccessResponse[TokenResponse],
    summary="Switch the current session to a different organization",
)
async def switch_organization(
    payload: SwitchOrganizationRequest, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    """Issues a fresh token pair scoped to a different organization the
    caller is a member of, without needing to log in again. Use this instead
    of `/auth/login` when a signed-in user wants to move between
    organizations they belong to.

    **Auth:** Bearer access token required (any authenticated user).

    **Errors:**
    - `UNAUTHORIZED` — missing/invalid/expired access token.
    - `FORBIDDEN` — the caller is not a member of the requested organization.
    """
    access_token, refresh_token = await auth_service.switch_organization(auth.user, payload.organization_id)
    return success_response(
        message="Switched organization", data=TokenResponse(access_token=access_token, refresh_token=refresh_token)
    )


@router.post(
    "/logout",
    response_model=SuccessResponse[None],
    summary="Revoke a refresh token",
)
async def logout(payload: LogoutRequest) -> dict:
    """Revokes the given refresh token so it can no longer be exchanged for
    new access tokens. Does not invalidate any access token already issued —
    those remain valid until they naturally expire.

    **Auth:** None required — the refresh token in the body is the
    credential being revoked.

    **Errors:**
    - `UNAUTHORIZED` — the token is malformed/expired, or has already been
      revoked/doesn't exist.
    """
    await auth_service.logout(payload.refresh_token)
    return success_response(message="Logged out")


# --- Internal, service-to-service introspection -----------------------------
# Lets another internal microservice (e.g. Agents) resolve
# user_id/organization_id/role from an access token without re-implementing
# JWT verification itself. Guarded by a shared internal API key, not a user
# JWT, since the caller here is a service.

internal_router = APIRouter(prefix="/internal", tags=["internal"])


class IntrospectRequest(BaseModel):
    access_token: str = Field(description="The access token to validate and resolve identity from.")


class IntrospectResponse(BaseModel):
    active: bool = Field(description="Whether the token is currently valid for an active user.")
    user_id: str | None = Field(default=None, description="The token's subject user id. `null` when `active` is false.")
    organization_id: str | None = Field(
        default=None, description="The organization the token is scoped to. `null` for a Super Admin or when `active` is false."
    )
    role: str | None = Field(default=None, description="The user's role, re-resolved from current membership (never trusted from the token). `null` when `active` is false, and for API tokens.")
    token_type: str = Field(default="user", description='`"user"` for a user access token, `"api_token"` for a Super-Admin-issued API token.')
    scopes: list[str] = Field(default_factory=list, description="What an API token may do (e.g. `agent-config:read`). Empty for user tokens.")
    token_id: str | None = Field(default=None, description="The API token's id. `null` for user tokens.")
    features: list[str] | None = Field(default=None, description="Product areas the token's organization may use, re-read on every call. `null` = unrestricted (Super Admins, API tokens).")


async def resolve_access_token(access_token: str) -> IntrospectResponse:
    """Resolves identity from an access token. Used by the introspection endpoint
    and called in-process by the Agents routers (see agents_service.core.http_client).
    """
    # API tokens (non-expiring, Super-Admin-issued) are opaque, not JWTs.
    if access_token.startswith(api_token_service.TOKEN_PREFIX):
        record = await api_token_service.resolve(access_token)
        if record is None:
            return IntrospectResponse(active=False)
        return IntrospectResponse(
            active=True, token_type="api_token", scopes=record.scopes, token_id=str(record.id)
        )

    try:
        claims = decode_token(access_token, settings.jwt_secret, settings.jwt_algorithm)
    except jwt.InvalidTokenError:
        return IntrospectResponse(active=False)

    if claims.get("type") != ACCESS_TOKEN_TYPE:
        return IntrospectResponse(active=False)

    user_id = claims.get("sub")
    if not user_id:
        return IntrospectResponse(active=False)

    # Never trust `role` from the token (there isn't one any more) — always
    # re-read the user and, for non-Super-Admins, the membership fresh, so a
    # disablement/role-change/removal-from-org takes effect immediately
    # instead of waiting out the access token's lifetime. See
    # users_service.core.deps.get_current_auth, which applies the same rule.
    try:
        user = await user_repo.get_by_id_global(PydanticObjectId(user_id))
    except Exception:
        return IntrospectResponse(active=False)
    if user is None or user.status != UserStatus.ACTIVE:
        return IntrospectResponse(active=False)

    if user.is_super_admin:
        # Carry the organization the Super Admin switched into, if it still exists.
        switched_org = await resolve_super_admin_org(claims.get("organization_id"))
        return IntrospectResponse(
            active=True,
            user_id=user_id,
            organization_id=str(switched_org) if switched_org else None,
            role="SUPER_ADMIN",
        )

    organization_id = claims.get("organization_id")
    if not organization_id:
        return IntrospectResponse(active=False)
    try:
        membership = await membership_repo.get(user.id, PydanticObjectId(organization_id))
    except Exception:
        return IntrospectResponse(active=False)
    if membership is None:
        return IntrospectResponse(active=False)

    org = await organization_repo.get_by_id(PydanticObjectId(organization_id))
    return IntrospectResponse(
        active=True, user_id=user_id, organization_id=organization_id, role=str(membership.role),
        features=[str(f) for f in org.features] if org else None,
    )


@internal_router.post(
    "/introspect",
    response_model=SuccessResponse[IntrospectResponse],
    summary="Resolve identity from an access token (service-to-service)",
)
async def introspect(
    payload: IntrospectRequest, x_internal_api_key: str | None = Header(default=None, description="Shared secret identifying an internal caller; must match this service's configured internal API key.")
) -> dict:
    """Lets another internal microservice (e.g. Agents) resolve
    `user_id`/`organization_id`/`role` from a user's access token without
    re-implementing JWT verification itself. Always returns HTTP 200 with
    `data.active` indicating validity — invalid, expired, or otherwise
    unusable tokens come back as `{"active": false}` rather than an error,
    since "not currently authenticated" is an expected, non-exceptional
    result for this endpoint. Role/org context is re-resolved from the
    user's current membership on every call, never read from a stale token
    claim, so a role change or removal from an organization is reflected
    immediately.

    **Auth:** Requires the `X-Internal-Api-Key` header to match this
    service's configured internal API key — not a user bearer token, since
    the caller here is a service, not an end user.

    **Errors:**
    - `UNAUTHORIZED` — `X-Internal-Api-Key` is missing or incorrect.
    """
    if x_internal_api_key != settings.internal_api_key:
        raise UnauthorizedError("Invalid internal API key")

    return success_response(data=await resolve_access_token(payload.access_token))
