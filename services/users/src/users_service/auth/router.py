import jwt
from common.errors import UnauthorizedError
from common.jwt import ACCESS_TOKEN_TYPE, decode_token
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Header, Request
from pydantic import BaseModel

from users_service.auth import service as auth_service
from users_service.auth.schema import (
    AccessTokenResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenResponse,
)
from users_service.core.config import get_settings
from users_service.core.rate_limit import limiter

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/login", response_model=SuccessResponse[TokenResponse])
@limiter.limit(settings.login_rate_limit)
async def login(request: Request, payload: LoginRequest) -> dict:
    _, access_token, refresh_token = await auth_service.login(payload.email, payload.password)
    return success_response(
        message="Logged in", data=TokenResponse(access_token=access_token, refresh_token=refresh_token)
    )


@router.post("/refresh", response_model=SuccessResponse[AccessTokenResponse])
async def refresh(payload: RefreshRequest) -> dict:
    access_token = await auth_service.refresh_access_token(payload.refresh_token)
    return success_response(message="Access token refreshed", data=AccessTokenResponse(access_token=access_token))


@router.post("/logout", response_model=SuccessResponse[None])
async def logout(payload: LogoutRequest) -> dict:
    await auth_service.logout(payload.refresh_token)
    return success_response(message="Logged out")


# --- Internal, service-to-service introspection -----------------------------
# Lets another internal microservice (e.g. the future Agents service) resolve
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

    return success_response(
        data=IntrospectResponse(
            active=True,
            user_id=claims.get("sub"),
            organization_id=claims.get("organization_id"),
            role=claims.get("role"),
        )
    )
