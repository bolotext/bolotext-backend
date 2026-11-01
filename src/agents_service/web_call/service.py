import json
import secrets
from datetime import timedelta

from beanie import PydanticObjectId
from common.errors import BadRequestError, ForbiddenError, NotFoundError
from livekit import api

from agents_service.agents import service as agent_service
from agents_service.agents.repository import get_by_id as get_agent_by_id
from agents_service.core.config import get_settings
from agents_service.core.deps import AuthContext
from agents_service.web_call.schema import Environment, WebCallToken

TOKEN_TTL = timedelta(minutes=10)


def _build_metadata(
    *, agent_id: str, environment: Environment, time_zone: str, test: bool, web_uuid: str, custom_variables: dict[str, str]
) -> str:
    """The participant metadata the voice agent reads in
    `VoicePipeline.parse_call_metadata`. A `type` of "inbound"/"outbound" makes
    the agent treat the call as a phone call, so web calls must NOT set it —
    keys here match the agent's web branch exactly."""
    return json.dumps(
        {
            "agent_id": agent_id,
            "environment": environment,
            "time_zone": time_zone,
            "test": test,
            "web_uuid": web_uuid,
            "personalized_link": "false",
            "custom_variables": [{"key": k, "value": v} for k, v in custom_variables.items()],
        }
    )


def mint_token(
    *,
    agent_id: str,
    environment: Environment,
    time_zone: str,
    test: bool,
    custom_variables: dict[str, str],
    display_name: str,
) -> WebCallToken:
    settings = get_settings()
    if not (settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret):
        raise BadRequestError("Web calls aren't configured: set LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET")

    suffix = secrets.token_hex(4)
    room_name = f"web-{agent_id[-6:]}-{suffix}"
    identity = f"web-{suffix}"
    metadata = _build_metadata(
        agent_id=agent_id,
        environment=environment,
        time_zone=time_zone,
        test=test,
        web_uuid=f"{'test' if test else 'embed'}-{suffix}",
        custom_variables=custom_variables,
    )
    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(identity)
        .with_name(display_name)
        .with_metadata(metadata)
        .with_ttl(TOKEN_TTL)
        .with_grants(
            api.VideoGrants(
                room=room_name,
                room_join=True,
                can_publish=True,
                can_publish_data=True,
                can_subscribe=True,
                can_update_own_metadata=False,
            )
        )
        .to_jwt()
    )
    return WebCallToken(
        server_url=settings.livekit_url, participant_token=token, room_name=room_name, agent_id=agent_id, environment=environment
    )


async def create_builder_token(agent_id: PydanticObjectId, auth: AuthContext, environment: Environment, time_zone: str, custom_variables: dict[str, str]) -> WebCallToken:
    # Ownership/role check; QA (view-only) may still place test calls.
    agent = await agent_service.get_owned_agent(agent_id, auth, write=False)
    return mint_token(
        agent_id=str(agent.id),
        environment=environment,
        time_zone=time_zone,
        test=True,
        custom_variables=custom_variables,
        display_name=f"user-{auth.user_id}",
    )


def _origin_allowed(origin: str | None, allowed: list[str]) -> bool:
    if not origin:
        return False
    origin = origin.rstrip("/").lower()
    for pattern in allowed:
        pattern = pattern.rstrip("/").lower()
        if pattern == origin:
            return True
        # Leading-subdomain wildcard only, e.g. https://*.example.com
        if "://*." in pattern:
            scheme, _, suffix = pattern.partition("://*.")
            o_scheme, _, o_host = origin.partition("://")
            if o_scheme == scheme and o_host.endswith("." + suffix):
                return True
    return False


async def create_public_token(agent_id: PydanticObjectId, parent_origin: str | None, time_zone: str, custom_variables: dict[str, str]) -> WebCallToken:
    agent = await get_agent_by_id(agent_id)
    # Same message for every failure so the endpoint can't be used to probe which agents exist.
    not_available = NotFoundError("This agent isn't available for web calls")
    if agent is None:
        raise not_available
    try:
        _, config = await agent_service.get_agent_environment_for_service(agent_id, "production")
    except NotFoundError:
        raise not_available from None
    if not config.deployment.chat_widget_enabled:
        raise not_available
    if not _origin_allowed(parent_origin, config.deployment.valid_origins):
        raise ForbiddenError("This site isn't allowed to embed this agent")
    return mint_token(
        agent_id=str(agent_id),
        environment="production",
        time_zone=time_zone,
        test=False,
        custom_variables=custom_variables,
        display_name="web-visitor",
    )
