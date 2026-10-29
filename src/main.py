import argparse
import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Hosts that import this file by path (e.g. Vercel) don't put src/ on sys.path,
# so the sibling packages (common, users_service, agents_service) wouldn't resolve.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402
from common.errors import register_exception_handlers  # noqa: E402
from common.responses import success_response  # noqa: E402
from common.schemas import SuccessResponse  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from starlette.datastructures import Headers  # noqa: E402
from starlette.types import ASGIApp, Receive, Scope, Send  # noqa: E402

from agents_service.app import API_DESCRIPTION as AGENTS_DESCRIPTION  # noqa: E402
from agents_service.app import TAGS_METADATA as AGENTS_TAGS  # noqa: E402
from agents_service.app import register_routes as register_agents_routes  # noqa: E402
from agents_service.db.mongodb import close_db as close_agents_db  # noqa: E402
from agents_service.db.mongodb import get_client as get_agents_client  # noqa: E402
from agents_service.db.mongodb import init_db as init_agents_db  # noqa: E402
from config import get_settings  # noqa: E402
from users_service.app import API_DESCRIPTION as USERS_DESCRIPTION  # noqa: E402
from users_service.app import TAGS_METADATA as USERS_TAGS  # noqa: E402
from users_service.app import register_routes as register_users_routes  # noqa: E402
from users_service.db.mongodb import close_db as close_users_db  # noqa: E402
from users_service.db.mongodb import get_client as get_users_client  # noqa: E402
from users_service.db.mongodb import init_db as init_users_db  # noqa: E402

settings = get_settings()
logging.basicConfig(level=settings.log_level)

API_DESCRIPTION = f"""
Single bolotext backend service: the Users (identity, organizations, RBAC) and
Agents (agent builder, providers, WhatsApp, call logs) APIs under one `/api/v1`.
Both used to be separate services behind an API gateway; the request/response
shapes, authentication and error envelope are unchanged. `GET /health` is the
liveness check.

# Users
{USERS_DESCRIPTION}

# Agents
{AGENTS_DESCRIPTION}
"""

PUBLIC_BASE_URL_HEADER = b"x-public-base-url"


def _public_base_url(scope: Scope) -> str:
    """The URL clients (and e.g. Twilio) use to reach this service: the pinned
    `PUBLIC_URL` if set, else the forwarded/Host header of this request.
    """
    if settings.public_url:
        return settings.public_url.rstrip("/")
    headers = Headers(scope=scope)
    scheme = headers.get("x-forwarded-proto", scope["scheme"]).split(",")[0].strip()
    host = headers.get("x-forwarded-host", headers.get("host", "")).split(",")[0].strip()
    return f"{scheme}://{host}"


class PublicBaseUrlMiddleware:
    """Sets `X-Public-Base-Url` on every request (read by the WhatsApp routes), as the
    API gateway used to — always overwritten, so a client-supplied value is never trusted.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = [(k, v) for k, v in scope["headers"] if k.lower() != PUBLIC_BASE_URL_HEADER]
            headers.append((PUBLIC_BASE_URL_HEADER, _public_base_url(scope).encode()))
            scope["headers"] = headers
        await self.app(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seeding is a separate, explicit step (`python src/main.py seed`), not part of boot.
    await init_users_db(get_users_client())
    await init_agents_db(get_agents_client())
    yield
    await close_agents_db()
    await close_users_db()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description=API_DESCRIPTION,
        openapi_tags=[{"name": "health", "description": "Service liveness check."}, *USERS_TAGS[1:], *AGENTS_TAGS[1:]],
        lifespan=lifespan,
    )
    app.add_middleware(PublicBaseUrlMiddleware)
    register_exception_handlers(app)
    register_users_routes(app)
    register_agents_routes(app)

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


async def _seed() -> None:
    from users_service.db.seed import seed_all

    await init_users_db(get_users_client())
    await seed_all()
    await close_users_db()


def main() -> None:
    parser = argparse.ArgumentParser(description="bolotext backend")
    parser.add_argument("command", nargs="?", default="serve", choices=["serve", "seed"])
    parser.add_argument("--log-level", default=settings.log_level.lower())
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level.upper())
    if args.command == "seed":
        asyncio.run(_seed())
        return

    # Reload is derived from ENVIRONMENT, never its own independent flag —
    # that's what makes "accidentally on in production" structurally
    # impossible rather than just discouraged. Reload mode is always
    # single-process, so WORKERS is only honored once it's off.
    reload = settings.environment.lower() == "development"
    workers = 1 if reload else settings.workers

    uvicorn.run(
        "main:app",
        app_dir="src",
        host=settings.host,
        port=settings.port,
        log_level=args.log_level.lower(),
        reload=reload,
        reload_dirs=["src"] if reload else None,
        workers=workers,
    )


if __name__ == "__main__":
    main()
