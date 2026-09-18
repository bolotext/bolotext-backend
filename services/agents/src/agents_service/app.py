import logging
from contextlib import asynccontextmanager

from common.errors import register_exception_handlers
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import FastAPI

from agents_service.actions.router import router as actions_router
from agents_service.agent_details.router import router as agent_details_router
from agents_service.agents.router import router as agents_router
from agents_service.analytics.router import router as analytics_router
from agents_service.core.config import get_settings
from agents_service.core.http_client import close_http_client
from agents_service.db.mongodb import close_db, get_client, init_db
from agents_service.deployment.router import router as deployment_router
from agents_service.faq.router import router as faq_router
from agents_service.flow.router import router as flow_router
from agents_service.llm.router import router as llm_router
from agents_service.mcp.router import router as mcp_router
from agents_service.others.router import router as others_router
from agents_service.prompt.router import router as prompt_router
from agents_service.providers.router import router as providers_router
from agents_service.transcriber.router import router as transcriber_router
from agents_service.voice_persona.router import router as voice_persona_router

settings = get_settings()
logging.basicConfig(level=settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(get_client())
    yield
    await close_db()
    await close_http_client()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
    register_exception_handlers(app)

    api_v1 = "/api/v1"
    # agents_router owns whole-agent operations (create/list/get/replace/delete/
    # publish/clone); every tab's own router owns its PATCH .../{section} route
    # (and, for prompt, the /test render endpoint) — see agents/model.py's
    # docstring for why the split follows the agent-builder's tabs.
    app.include_router(agents_router, prefix=api_v1)
    app.include_router(agent_details_router, prefix=api_v1)
    app.include_router(prompt_router, prefix=api_v1)
    app.include_router(flow_router, prefix=api_v1)
    app.include_router(transcriber_router, prefix=api_v1)
    app.include_router(llm_router, prefix=api_v1)
    app.include_router(voice_persona_router, prefix=api_v1)
    app.include_router(analytics_router, prefix=api_v1)
    app.include_router(others_router, prefix=api_v1)
    app.include_router(faq_router, prefix=api_v1)
    app.include_router(deployment_router, prefix=api_v1)
    app.include_router(actions_router, prefix=api_v1)
    app.include_router(mcp_router, prefix=api_v1)
    app.include_router(providers_router, prefix=api_v1)

    @app.get("/health", tags=["health"], response_model=SuccessResponse[dict])
    async def health() -> dict:
        return success_response(data={"service": settings.app_name})

    return app


app = create_app()
