from common.enums import Role
from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    # Only needed when the account belongs to more than one organization and
    # the first login attempt (without it) came back with `organizations`
    # instead of tokens.
    organization_id: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class SwitchOrganizationRequest(BaseModel):
    organization_id: str


class OrganizationChoice(BaseModel):
    organization_id: str
    name: str
    role: Role


class LoginResponse(BaseModel):
    """Either a token pair, or — when the account has more than one
    organization membership and the request didn't say which one —
    `organizations` alone, so the client can re-call /auth/login with
    `organization_id` set.
    """

    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    organizations: list[OrganizationChoice] | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
