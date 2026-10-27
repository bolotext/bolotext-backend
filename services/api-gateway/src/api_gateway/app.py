import logging
from contextlib import asynccontextmanager

import httpx
from common.errors import NotFoundError, register_exception_handlers
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import FastAPI, Request, Response

from api_gateway.config import get_settings
from api_gateway.proxy import forward

settings = get_settings()
logging.basicConfig(level=settings.log_level)

API_DESCRIPTION = """
Single public entry point that reverse-proxies `/api/v1/*` to the Users and
Agents services based on the first path segment (see `_route_map` below),
forwarding method, headers, query string and body unchanged and passing the
upstream response straight back. It adds no auth, validation or logic of its
own — the request/response shape, authentication requirements and error
envelope for a given path are entirely defined by the upstream service that
owns it (see the Users and Agents services' own `/docs`).

`GET /health` is the only endpoint implemented directly by the gateway
itself; everything else under `/api/v1` is proxied. Currently proxied first
path segments: `auth`, `organizations`, `users`, `api-tokens`, `internal` (Users service),
and `agents`, `providers`, `agent-templates` (Agents service) — see `_route_map` below.
"""


def _route_map() -> dict[str, str | None]:
    """First path segment under /api/v1/ -> upstream service base URL."""
    return {
        "auth": settings.users_service_url,
        "organizations": settings.users_service_url,
        "users": settings.users_service_url,
        "internal": settings.users_service_url,
        "api-tokens": settings.users_service_url,  # users_service.api_tokens — Super-Admin-issued API tokens
        "agents": settings.agents_service_url,  # None until that service exists
        "providers": settings.agents_service_url,  # agents_service.providers — LLM/STT/TTS provider+model registry
        "agent-templates": settings.agents_service_url,  # agents_service.agent_templates — starter agent templates
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(timeout=settings.upstream_timeout_seconds)
    yield
    await app.state.http_client.aclose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description=API_DESCRIPTION,
        openapi_tags=[
            {"name": "health", "description": "Gateway liveness check."},
            {"name": "proxy", "description": "Catch-all reverse proxy to the upstream services — see the service description above."},
        ],
        lifespan=lifespan,
    )
    register_exception_handlers(app)

    @app.get(
        "/health",
        tags=["health"],
        response_model=SuccessResponse[dict],
        summary="Health check",
    )
    async def health() -> dict:
        """Returns 200 with the service name if the gateway process is up.
        Does not check that the upstream services it proxies to are
        reachable — use it only for liveness, not readiness."""
        return success_response(data={"service": settings.app_name})

    @app.api_route(
        "/api/v1/{full_path:path}",
        methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        tags=["proxy"],
        summary="Proxy to the upstream service",
    )
    async def proxy_v1(full_path: str, request: Request) -> Response:
        """Forwards this request as-is to whichever upstream service owns
        `full_path`'s first segment (see `_route_map`), and returns that
        service's response unchanged — method, headers, query string, body,
        status code and all. This route's own request/response schema here
        is a generic passthrough; refer to the owning service's `/docs` for
        the real shape, auth requirements and errors of the path you're
        calling.

        **Errors:** `NOT_FOUND` — the first path segment isn't mapped to any
        upstream service in `_route_map`. Any other error is whatever the
        upstream service itself returned, forwarded unchanged.
        """
        first_segment = full_path.split("/", 1)[0]
        upstream_base = _route_map().get(first_segment)
        if not upstream_base:
            raise NotFoundError(f"No service is registered for /api/v1/{first_segment}")

        return await forward(
            request.app.state.http_client, request, upstream_base, f"/api/v1/{full_path}"
        )

    return app


app = create_app()
