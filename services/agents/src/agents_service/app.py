import logging
from contextlib import asynccontextmanager

from common.enums import Feature
from common.errors import register_exception_handlers
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import Depends, FastAPI

from agents_service.actions.router import router as actions_router
from agents_service.agent_assignments.router import router as agent_assignments_router
from agents_service.agent_details.router import router as agent_details_router
from agents_service.agent_templates.router import router as agent_templates_router
from agents_service.agents.router import agent_config_router, router as agents_router
from agents_service.call_logs.router import router as call_logs_router
from agents_service.analytics.router import router as analytics_router
from agents_service.core.config import get_settings
from agents_service.core.deps import bind_write_environment, require_feature
from agents_service.core.http_client import close_http_client
from agents_service.db.mongodb import close_db, get_client, init_db
from agents_service.deployment.router import router as deployment_router
from agents_service.dynamic_message.router import router as dynamic_message_router
from agents_service.faq.router import router as faq_router
from agents_service.flow.router import router as flow_router
from agents_service.languages.router import router as languages_router
from agents_service.llm.router import router as llm_router
from agents_service.mcp.router import router as mcp_router
from agents_service.others.router import router as others_router
from agents_service.post_call_trigger.router import router as post_call_trigger_router
from agents_service.precall_variables.router import router as precall_variables_router
from agents_service.prompt.router import router as prompt_router
from agents_service.providers.router import router as providers_router
from agents_service.transcriber.router import router as transcriber_router
from agents_service.voice_persona.router import router as voice_persona_router
from agents_service.whatsapp.router import router as whatsapp_router, status_router as whatsapp_status_router

settings = get_settings()
logging.basicConfig(level=settings.log_level)

API_DESCRIPTION = """
Agent management service: CRUD, configuration and publishing for voice/chat
agents, plus the shared LLM/STT/TTS provider+model registry.

## Authentication
Every endpoint except `/health` requires a bearer access token issued by the
Users service: `Authorization: Bearer <access_token>`. This service does not
verify the token itself — it calls the Users service's internal introspection
endpoint on every request, so a disabled user or a role/membership change
takes effect immediately, not when the token happens to expire.

## Response envelope
Every response — success or error — is returned with **HTTP 200** and the
same JSON envelope: `{"status", "code", "message", "data"}` on success or
`{"status", "code", "message", "errors"}` on error. `code` carries the real
logical status (e.g. `404`) and `errors.type` a stable machine-readable error
code (e.g. `NOT_FOUND`); clients must branch on the response body, not the
HTTP transport status. See each endpoint's **Errors** section for the error
`type` values it can return.

## Environments
An agent has three environments: `development` (edited directly by every
section's own PATCH route), and `stage`/`production` (read-only snapshots,
written only by the `/move-to-stage` and `/move-to-prod` promotion routes).
"""

TAGS_METADATA = [
    {"name": "health", "description": "Service liveness check."},
    {
        "name": "agents",
        "description": "Whole-agent lifecycle: create, list, get, delete, status, "
        "environments, and promotion between environments.",
    },
    {"name": "call-logs", "description": "Finished-call logs posted by the voice runtime, and their per-agent history."},
    {"name": "agents:agent-details", "description": "Identity/basics section of the agent builder (name, description, region, timezone, bot type)."},
    {"name": "agents:languages", "description": "Configured languages for an agent."},
    {"name": "agents:precall-variables", "description": "Variables resolved before a call starts and made available to the prompt/flow."},
    {"name": "agents:prompt", "description": "System prompt content, versioning, language-switch behavior, and prompt test-rendering."},
    {"name": "agents:flow", "description": "Conversation flow configuration."},
    {"name": "agents:transcriber", "description": "Speech-to-text (ASR) provider and tuning settings."},
    {"name": "agents:llm", "description": "LLM provider and generation settings for the agent."},
    {"name": "agents:voice-persona", "description": "Text-to-speech voice and persona settings."},
    {"name": "agents:analytics", "description": "Call analytics configuration, including the post-call trigger webhook."},
    {"name": "agents:others", "description": "Miscellaneous agent settings that don't belong to a dedicated tab."},
    {"name": "agents:faq", "description": "FAQ entries the agent can draw on during a call."},
    {"name": "agents:deployment", "description": "Deployment/channel settings for publishing an agent."},
    {"name": "agents:dynamic-message", "description": "Dynamic, templated messages the agent can send during a call."},
    {"name": "agents:post-call-trigger", "description": "Webhook fired after a call ends."},
    {"name": "agents:actions", "description": "Custom actions/functions the agent can invoke during a call."},
    {"name": "agents:mcp", "description": "Model Context Protocol server integrations available to the agent."},
    {"name": "agents:assignments", "description": "Assigning agents to users/teams."},
    {"name": "whatsapp", "description": "WhatsApp Business messaging via Twilio: agents, templates + approval, CSV contacts, sending and delivery status."},
    {"name": "providers", "description": "Read-only registry of available LLM/STT/TTS providers and models."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(get_client())
    yield
    await close_db()
    await close_http_client()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description=API_DESCRIPTION,
        openapi_tags=TAGS_METADATA,
        lifespan=lifespan,
    )
    register_exception_handlers(app)

    api_v1 = "/api/v1"
    # agents_router owns whole-agent operations (create/list/get/replace/delete/
    # publish/clone); every tab's own router owns its PATCH .../{section} route
    # (and, for prompt, the /test render endpoint) — see agents/model.py's
    # docstring for why the split follows the agent-builder's tabs.
    # Every router binds `?env=` (which environment edit routes write to) except
    # the config router: GET /agents/config has its own `environment` param.
    write_env = [Depends(bind_write_environment)]
    # Everything below except WhatsApp/SMS is the Voice Agents product, which a Super Admin
    # can switch off per organization (WhatsApp and SMS are checked per agent channel).
    voice = [Depends(require_feature(Feature.VOICE_AGENTS))]
    voice_env = write_env + voice
    app.include_router(agent_config_router, prefix=api_v1, dependencies=voice)
    app.include_router(call_logs_router, prefix=api_v1, dependencies=voice)
    app.include_router(agent_templates_router, prefix=api_v1, dependencies=voice_env)
    app.include_router(agents_router, prefix=api_v1, dependencies=voice_env)
    app.include_router(agent_assignments_router, prefix=api_v1, dependencies=voice_env)
    app.include_router(agent_details_router, prefix=api_v1, dependencies=voice_env)
    app.include_router(languages_router, prefix=api_v1, dependencies=voice_env)
    app.include_router(precall_variables_router, prefix=api_v1, dependencies=voice_env)
    app.include_router(prompt_router, prefix=api_v1, dependencies=voice_env)
    app.include_router(flow_router, prefix=api_v1, dependencies=voice_env)
    app.include_router(transcriber_router, prefix=api_v1, dependencies=voice_env)
    app.include_router(llm_router, prefix=api_v1, dependencies=voice_env)
    app.include_router(voice_persona_router, prefix=api_v1, dependencies=voice_env)
    app.include_router(analytics_router, prefix=api_v1, dependencies=voice_env)
    app.include_router(others_router, prefix=api_v1, dependencies=voice_env)
    app.include_router(faq_router, prefix=api_v1, dependencies=voice_env)
    app.include_router(deployment_router, prefix=api_v1, dependencies=voice_env)
    app.include_router(dynamic_message_router, prefix=api_v1, dependencies=voice_env)
    app.include_router(post_call_trigger_router, prefix=api_v1, dependencies=voice_env)
    app.include_router(actions_router, prefix=api_v1, dependencies=voice_env)
    app.include_router(mcp_router, prefix=api_v1, dependencies=voice_env)
    app.include_router(providers_router, prefix=api_v1, dependencies=voice_env)
    app.include_router(whatsapp_router, prefix=api_v1)
    app.include_router(whatsapp_status_router, prefix=api_v1)

    @app.get(
        "/health",
        tags=["health"],
        response_model=SuccessResponse[dict],
        summary="Health check",
    )
    async def health() -> dict:
        """Returns 200 with the service name if the process is up. Does not
        check downstream dependencies (MongoDB, the Users service) — use it
        only for liveness, not readiness."""
        return success_response(data={"service": settings.app_name})

    return app


app = create_app()
