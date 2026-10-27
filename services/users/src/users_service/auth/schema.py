from common.enums import Role
from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"credential": "<google-id-token>"}}
    )

    credential: str = Field(description="The Google ID token (JWT) returned by Google Sign-In.")
    # Only needed when the account belongs to more than one organization and
    # the first login attempt (without it) came back with `organizations`
    # instead of tokens.
    organization_id: str | None = Field(
        default=None,
        description="Which organization to log into. Only required on a second attempt, after a "
        "first login without it returned `organizations` instead of tokens because the account "
        "belongs to more than one.",
    )


class RefreshRequest(BaseModel):
    refresh_token: str = Field(description="A refresh token previously issued by `POST /auth/login`.")


class LogoutRequest(BaseModel):
    refresh_token: str = Field(description="The refresh token to revoke.")


class SwitchOrganizationRequest(BaseModel):
    organization_id: str = Field(description="The organization to switch the current session into.")


class OrganizationChoice(BaseModel):
    organization_id: str = Field(description="The organization's id.")
    name: str = Field(description="The organization's display name.")
    role: Role = Field(description="The caller's role within this organization.")


class LoginResponse(BaseModel):
    """Either a token pair, or — when the account has more than one
    organization membership and the request didn't say which one —
    `organizations` alone, so the client can re-call /auth/login with
    `organization_id` set.
    """

    access_token: str | None = Field(default=None, description="Short-lived bearer token for authenticated requests. `null` when `organizations` is returned instead.")
    refresh_token: str | None = Field(default=None, description="Long-lived token used with `POST /auth/refresh` to obtain a new access token. `null` when `organizations` is returned instead.")
    token_type: str = Field(default="bearer", description="Always `\"bearer\"`.")
    organizations: list[OrganizationChoice] | None = Field(
        default=None,
        description="Present instead of tokens when the account belongs to more than one "
        "organization and the request didn't specify `organization_id`. Pick one and retry.",
    )


class TokenResponse(BaseModel):
    access_token: str = Field(description="Short-lived bearer token, scoped to the newly selected organization.")
    refresh_token: str = Field(description="Long-lived token used with `POST /auth/refresh` to obtain a new access token.")
    token_type: str = Field(default="bearer", description="Always `\"bearer\"`.")


class AccessTokenResponse(BaseModel):
    access_token: str = Field(description="Newly issued short-lived bearer token.")
    token_type: str = Field(default="bearer", description="Always `\"bearer\"`.")
