import logging
from contextlib import asynccontextmanager

from common.errors import register_exception_handlers
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seeding is a separate, explicit step (`python main.py seed`) — run it
    # yourself before `serve` locally, or via services/users/entrypoint.sh in
    # Docker, which already runs `seed` then `serve`. It doesn't belong here:
    # every app boot would otherwise re-run it, which surprised local dev.
    await init_db(get_client())
    yield
    await close_db()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    register_exception_handlers(app)

    api_v1 = "/api/v1"
    app.include_router(auth_router, prefix=api_v1)
    app.include_router(organizations_router, prefix=api_v1)
    app.include_router(memberships_router, prefix=api_v1)
    app.include_router(users_router, prefix=api_v1)
    app.include_router(auth_internal_router, prefix=api_v1)

    @app.get("/health", tags=["health"], response_model=SuccessResponse[dict])
    async def health() -> dict:
        return success_response(data={"service": settings.app_name})

    return app


app = create_app()
