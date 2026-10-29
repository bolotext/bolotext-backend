from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends, Path, Query

from agents_service.call_logs import service
from agents_service.call_logs.schema import CallLogIn, CallLogListOut, CallLogOut, CallLogStored
from agents_service.core.deps import AuthContext, ServiceAuth, get_call_log_writer, get_current_auth

router = APIRouter(tags=["call-logs"])

_AGENT_ID = Path(description="The voice agent's id.")


@router.post("/call-logs", response_model=SuccessResponse[CallLogStored], summary="Store a finished call's log (voice runtime)")
async def create_call_log(payload: CallLogIn, _: ServiceAuth = Depends(get_call_log_writer)) -> dict:
    """Called by the voice runtime when a call ends. Stores the interaction
    (details, token usage, the full conversation journey) against the agent.
    Posting the same `session_id` for the same agent again updates the stored
    log instead of creating a duplicate, so retries are safe.

    **Auth:** a non-expiring API token with the `call-log:write` scope
    (created by a Super Admin under "API tokens"); user tokens are rejected.

    **Errors:**
    - `UNAUTHORIZED` — missing/invalid token, or a user token.
    - `FORBIDDEN` — the API token lacks the `call-log:write` scope.
    - `NOT_FOUND` — no agent with this `agent_id`.
    - `UNPROCESSABLE_ENTITY` — `call_payload.interaction` is missing.
    """
    res = await service.ingest(payload.agent_id, payload.call_payload)
    return success_response(code=201 if res.created else 200, message="Call log stored", data=res)


@router.get("/agents/{agent_id}/call-logs", response_model=SuccessResponse[CallLogListOut], summary="List an agent's call logs")
async def list_call_logs(
    agent_id: PydanticObjectId = _AGENT_ID,
    q: str | None = Query(None, description="Search session id, phone numbers or web token."),
    status: str | None = Query(None, description="e.g. completed, missed, busy, failed."),
    source: str | None = Query(None, description="phone, website or personalized_link."),
    test: bool | None = Query(None, description="Only test calls (true) or only real calls (false)."),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    """Newest calls first, without the conversation (open one for that).

    **Auth:** bearer JWT; same access as viewing the agent.

    **Errors:**
    - `NOT_FOUND` — no such agent, or one the caller can't access.
    """
    return success_response(
        data=await service.list_logs(agent_id, auth, q=q, status=status, source=source, test=test, skip=skip, limit=limit)
    )


@router.get("/agents/{agent_id}/call-logs/{log_id}", response_model=SuccessResponse[CallLogOut], summary="Get one call log with its conversation")
async def get_call_log(
    log_id: str = Path(description="The call log's id."),
    agent_id: PydanticObjectId = _AGENT_ID,
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    """The stored interaction: details, hang-up reason, token usage and the
    full conversation journey.

    **Auth:** bearer JWT; same access as viewing the agent.

    **Errors:**
    - `NOT_FOUND` — no such agent or call log in the caller's reach.
    """
    return success_response(data=await service.get_log(agent_id, log_id, auth))
