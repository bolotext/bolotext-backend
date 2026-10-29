"""Identity resolution for this service. Users and Agents now run in one
process, so the access token is resolved by calling the Users service's
introspection logic in-process instead of over HTTP — see
agents_service.core.deps for how the result is used.
"""

from pydantic import BaseModel

from users_service.auth.router import resolve_access_token


class IntrospectResult(BaseModel):
    active: bool
    user_id: str | None = None
    organization_id: str | None = None
    role: str | None = None
    # "api_token" for a Super-Admin-issued, non-expiring service token (see
    # the Users service's /api-tokens); those carry `scopes` instead of a
    # user/role identity.
    token_type: str = "user"
    scopes: list[str] = []
    token_id: str | None = None
    # Product areas the caller's organization may use; None = unrestricted.
    features: list[str] | None = None


async def introspect(access_token: str) -> IntrospectResult:
    return IntrospectResult(**(await resolve_access_token(access_token)).model_dump())
