import logging
from contextlib import asynccontextmanager

from common.errors import register_exception_handlers
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded

from users_service.api_tokens.router import router as api_tokens_router
from users_service.auth.router import internal_router as auth_internal_router
from users_service.auth.router import router as auth_router
from users_service.core.config import get_settings
from users_service.core.rate_limit import limiter, rate_limit_exceeded_handler
from users_service.db.mongodb import close_db, get_client, init_db
from users_service.memberships.router import router as memberships_router
from users_service.organizations.router import router as organizations_router
from users_service.users.router import router as users_router

settings = get_settings()
logging.basicConfig(level=settings.log_level)

API_DESCRIPTION = """
Identity service: login and token issuance, organizations, memberships, and
users. Other internal services (e.g. Agents) resolve identity from an access
token via `/api/v1/internal/introspect` rather than verifying JWTs locally.

## Authentication
Most endpoints require a bearer access token: `Authorization: Bearer
<access_token>`, obtained from `POST /auth/login`. `POST /auth/login`,
`POST /auth/refresh`, `POST /auth/logout`, and `POST /internal/introspect`
do not require one — `/internal/introspect` is instead guarded by a shared
internal API key (`X-Internal-Api-Key` header), since its caller is another
service, not a user.

Endpoints beyond simple "must be logged in" also require a specific
permission (e.g. `user.create`) or role, evaluated against the caller's
membership in the organization their access token is scoped to; see each
endpoint's **Auth** note.

## Response envelope
Every response — success or error — is returned with **HTTP 200** and the
same JSON envelope: `{"status", "code", "message", "data"}` on success or
`{"status", "code", "message", "errors"}` on error. `code` carries the real
logical status (e.g. `404`) and `errors.type` a stable machine-readable error
code (e.g. `NOT_FOUND`); clients must branch on the response body, not the
HTTP transport status. See each endpoint's **Errors** section for the error
`type` values it can return.
"""

TAGS_METADATA = [
    {"name": "health", "description": "Service liveness check."},
    {"name": "auth", "description": "Login, token refresh/logout, and organization switching."},
    {"name": "organizations", "description": "Tenant organizations."},
    {"name": "memberships", "description": "A user's role within an organization."},
    {"name": "users", "description": "User accounts."},
    {
        "name": "internal",
        "description": "Service-to-service endpoints, guarded by an internal API key "
        "instead of a user access token. Not for use by end-user clients.",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seeding is a separate, explicit step (`python main.py seed`) — run it
    # yourself before `serve` locally, or via services/users/entrypoint.sh in
    # Docker, which already runs `seed` then `serve`. It doesn't belong here:
    # every app boot would otherwise re-run it, which surprised local dev.
    await init_db(get_client())
    yield
    await close_db()


def register_routes(app: FastAPI) -> None:
    """Rate limiting and the Users routers; shared by this app and the combined backend app."""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    api_v1 = "/api/v1"
    app.include_router(auth_router, prefix=api_v1)
    app.include_router(organizations_router, prefix=api_v1)
    app.include_router(memberships_router, prefix=api_v1)
    app.include_router(users_router, prefix=api_v1)
    app.include_router(api_tokens_router, prefix=api_v1)
    app.include_router(auth_internal_router, prefix=api_v1)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description=API_DESCRIPTION,
        openapi_tags=TAGS_METADATA,
        lifespan=lifespan,
    )

    register_exception_handlers(app)
    register_routes(app)

    @app.get(
        "/health",
        tags=["health"],
        response_model=SuccessResponse[dict],
        summary="Health check",
    )
    async def health() -> dict:
        """Returns 200 with the service name if the process is up. Does not
        check downstream dependencies (MongoDB) — use it only for liveness,
        not readiness."""
        return success_response(data={"service": settings.app_name})

    return app


app = create_app()
