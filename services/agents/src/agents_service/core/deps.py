from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal

from common.enums import Role
from common.errors import UnauthorizedError
from common.log_utils import setup_logger
from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agents_service.core.http_client import introspect

logger = setup_logger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)

# Which environment's AgentConfig this request's edit routes write to — set
# once per request by `bind_write_environment` (app-level dependency) from the
# `?env=` query param, read by agents.service.get_agent_with_config.
# `production` is deliberately not accepted: it is only ever written by
# promotion from stage.
write_environment: ContextVar[Literal["development", "stage"]] = ContextVar("write_environment", default="development")


async def bind_write_environment(
    env: Literal["development", "stage"] = Query(
        "development", description="Environment an edit route writes to. `production` is promote-only."
    ),
) -> None:
    write_environment.set(env)


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
