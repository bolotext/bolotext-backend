from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends, Path

from agents_service.core.deps import AuthContext, get_current_auth
from agents_service.web_call import service
from agents_service.web_call.schema import PublicWebCallTokenRequest, WebCallToken, WebCallTokenRequest

router = APIRouter(prefix="/agents", tags=["agents:web-call"])
# No auth: called by the embeddable widget on third-party sites.
public_router = APIRouter(prefix="/public/agents", tags=["agents:web-call"])


@router.post(
    "/{agent_id}/web-call/token",
    response_model=SuccessResponse[WebCallToken],
    summary="Get a LiveKit token to place a test web call to this agent",
)
async def create_web_call_token(
    payload: WebCallTokenRequest,
    agent_id: PydanticObjectId = Path(description="The agent's id."),
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    """Mints a short-lived LiveKit token. The agent id, environment, time zone
    and any `custom_variables` ride in the participant metadata, which is how
    the voice agent knows which agent's config to load — so the same call
    works for any agent.

    **Auth:** Bearer JWT; the caller must have access to the agent.

    **Errors:** `NOT_FOUND`, `UNAUTHORIZED`, `BAD_REQUEST` (LiveKit not configured).
    """
    data = await service.create_builder_token(agent_id, auth, payload.environment, payload.time_zone, payload.custom_variables)
    return success_response(message="Web call token created", data=data)


@public_router.post(
    "/{agent_id}/web-call/token",
    response_model=SuccessResponse[WebCallToken],
    summary="Get a LiveKit token for the embeddable voice widget",
)
async def create_public_web_call_token(
    payload: PublicWebCallTokenRequest,
    agent_id: PydanticObjectId = Path(description="The agent's id."),
) -> dict:
    """Unauthenticated. Only works when the agent's **production** deployment
    has the widget enabled and `parent_origin` is in its allowed origins.

    **Errors:** `NOT_FOUND` (not enabled / not promoted), `FORBIDDEN` (origin not allowed).
    """
    data = await service.create_public_token(agent_id, payload.parent_origin, payload.time_zone, payload.custom_variables)
    return success_response(message="Web call token created", data=data)
