from dataclasses import dataclass

from common.enums import Role
from common.errors import UnauthorizedError
from common.log_utils import setup_logger
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agents_service.core.http_client import introspect

logger = setup_logger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    organization_id: str | None
    role: Role

    @property
    def is_super_admin(self) -> bool:
        return self.role == Role.SUPER_ADMIN


async def get_current_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthContext:
    if credentials is None:
        raise UnauthorizedError("Missing bearer token")

    result = await introspect(credentials.credentials)
    if not result.active or not result.user_id or not result.role:
        raise UnauthorizedError("Invalid or expired access token")

    return AuthContext(user_id=result.user_id, organization_id=result.organization_id, role=Role(result.role))
