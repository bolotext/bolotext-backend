import jwt
from beanie import PydanticObjectId
from common.errors import UnauthorizedError
from common.jwt import ACCESS_TOKEN_TYPE, decode_token
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel

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
from users_service.core.deps import AuthContext, get_current_auth
from users_service.core.rate_limit import limiter
from users_service.enums import UserStatus
from users_service.memberships import repository as membership_repo
from users_service.users import repository as user_repo

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/login", response_model=SuccessResponse[LoginResponse])
@limiter.limit(settings.login_rate_limit)
async def login(request: Request, payload: LoginRequest) -> dict:
    result = await auth_service.login(payload.email, payload.password, payload.organization_id)
    if result.requires_selection:
        return success_response(
            message="Select an organization to continue",
            data=LoginResponse(organizations=result.organizations),
        )
    return success_response(
        message="Logged in",
        data=LoginResponse(access_token=result.access_token, refresh_token=result.refresh_token),
    )


@router.post("/refresh", response_model=SuccessResponse[AccessTokenResponse])
async def refresh(payload: RefreshRequest) -> dict:
    access_token = await auth_service.refresh_access_token(payload.refresh_token)
    return success_response(message="Access token refreshed", data=AccessTokenResponse(access_token=access_token))


@router.post("/switch-organization", response_model=SuccessResponse[TokenResponse])
async def switch_organization(
    payload: SwitchOrganizationRequest, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    access_token, refresh_token = await auth_service.switch_organization(auth.user, payload.organization_id)
    return success_response(
        message="Switched organization", data=TokenResponse(access_token=access_token, refresh_token=refresh_token)
    )


@router.post("/logout", response_model=SuccessResponse[None])
async def logout(payload: LogoutRequest) -> dict:
    await auth_service.logout(payload.refresh_token)
    return success_response(message="Logged out")


# --- Internal, service-to-service introspection -----------------------------
# Lets another internal microservice (e.g. Agents) resolve
# user_id/organization_id/role from an access token without re-implementing
# JWT verification itself. Guarded by a shared internal API key, not a user
# JWT, since the caller here is a service.

internal_router = APIRouter(prefix="/internal", tags=["internal"])


class IntrospectRequest(BaseModel):
    access_token: str


class IntrospectResponse(BaseModel):
    active: bool
    user_id: str | None = None
    organization_id: str | None = None
    role: str | None = None


@internal_router.post("/introspect", response_model=SuccessResponse[IntrospectResponse])
async def introspect(
    payload: IntrospectRequest, x_internal_api_key: str | None = Header(default=None)
) -> dict:
    if x_internal_api_key != settings.internal_api_key:
        raise UnauthorizedError("Invalid internal API key")

    try:
        claims = decode_token(payload.access_token, settings.jwt_secret, settings.jwt_algorithm)
    except jwt.InvalidTokenError:
        return success_response(data=IntrospectResponse(active=False))

    if claims.get("type") != ACCESS_TOKEN_TYPE:
        return success_response(data=IntrospectResponse(active=False))

    user_id = claims.get("sub")
    if not user_id:
        return success_response(data=IntrospectResponse(active=False))

    # Never trust `role` from the token (there isn't one any more) — always
    # re-read the user and, for non-Super-Admins, the membership fresh, so a
    # disablement/role-change/removal-from-org takes effect immediately
    # instead of waiting out the access token's lifetime. See
    # users_service.core.deps.get_current_auth, which applies the same rule.
    try:
        user = await user_repo.get_by_id_global(PydanticObjectId(user_id))
    except Exception:
        return success_response(data=IntrospectResponse(active=False))
    if user is None or user.status != UserStatus.ACTIVE:
        return success_response(data=IntrospectResponse(active=False))

    if user.is_super_admin:
        return success_response(
            data=IntrospectResponse(active=True, user_id=user_id, organization_id=None, role="SUPER_ADMIN")
        )

    organization_id = claims.get("organization_id")
    if not organization_id:
        return success_response(data=IntrospectResponse(active=False))
    try:
        membership = await membership_repo.get(user.id, PydanticObjectId(organization_id))
    except Exception:
        return success_response(data=IntrospectResponse(active=False))
    if membership is None:
        return success_response(data=IntrospectResponse(active=False))

    return success_response(
        data=IntrospectResponse(active=True, user_id=user_id, organization_id=organization_id, role=str(membership.role))
    )
