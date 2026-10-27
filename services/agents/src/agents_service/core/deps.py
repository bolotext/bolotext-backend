from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal

from common.enums import Role
from common.errors import ForbiddenError, UnauthorizedError
from common.log_utils import setup_logger
from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from agents_service.core.http_client import IntrospectResult, introspect

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


AGENT_CONFIG_READ = "agent-config:read"


@dataclass(frozen=True)
class ServiceAuth:
    """A Super-Admin-issued API token (e.g. the voice agent). It has no user
    identity or ownership, only the scopes it was issued with, and is accepted
    only by routes that ask for it (see `get_config_auth`).
    """

    token_id: str
    scopes: frozenset[str]


async def get_introspection(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> IntrospectResult:
    if credentials is None:
        raise UnauthorizedError("Missing bearer token")
    return await introspect(credentials.credentials)


async def get_current_auth(result: IntrospectResult = Depends(get_introspection)) -> AuthContext:
    if not result.active:
        raise UnauthorizedError("Invalid or expired access token")
    if result.token_type != "user":
        raise UnauthorizedError("API tokens can't be used on this endpoint")
    if not result.user_id or not result.role:
        raise UnauthorizedError("Invalid or expired access token")

    return AuthContext(user_id=result.user_id, organization_id=result.organization_id, role=Role(result.role))


async def get_config_auth(result: IntrospectResult = Depends(get_introspection)) -> AuthContext | ServiceAuth:
    """For routes that serve agent configs: a normal user (ownership-checked
    by the service layer) or an API token carrying `agent-config:read`.
    """
    if result.active and result.token_type == "api_token":
        if AGENT_CONFIG_READ not in result.scopes:
            raise ForbiddenError("This API token can't read agent configs")
        return ServiceAuth(token_id=result.token_id or "", scopes=frozenset(result.scopes))
    return await get_current_auth(result)
