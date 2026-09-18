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


def _route_map() -> dict[str, str | None]:
    """First path segment under /api/v1/ -> upstream service base URL."""
    return {
        "auth": settings.users_service_url,
        "organizations": settings.users_service_url,
        "users": settings.users_service_url,
        "internal": settings.users_service_url,
        "agents": settings.agents_service_url,  # None until that service exists
        "providers": settings.agents_service_url,  # agents_service.providers — LLM/STT/TTS provider+model registry
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(timeout=settings.upstream_timeout_seconds)
    yield
    await app.state.http_client.aclose()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
    register_exception_handlers(app)

    @app.get("/health", tags=["health"], response_model=SuccessResponse[dict])
    async def health() -> dict:
        return success_response(data={"service": settings.app_name})

    @app.api_route(
        "/api/v1/{full_path:path}",
        methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    )
    async def proxy_v1(full_path: str, request: Request) -> Response:
        first_segment = full_path.split("/", 1)[0]
        upstream_base = _route_map().get(first_segment)
        if not upstream_base:
            raise NotFoundError(f"No service is registered for /api/v1/{first_segment}")

        return await forward(
            request.app.state.http_client, request, upstream_base, f"/api/v1/{full_path}"
        )

    return app


app = create_app()
