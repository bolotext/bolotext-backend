import re
from datetime import datetime, timezone

from beanie import PydanticObjectId
from common.errors import NotFoundError, UnprocessableEntityError
from common.log_utils import setup_logger

from agents_service.agents import service as agent_service
from agents_service.agents.model import Agent
from agents_service.call_logs.model import CallLog
from agents_service.call_logs.schema import CallLogListOut, CallLogOut, CallLogStored, CallLogSummary
from agents_service.core.deps import AuthContext

logger = setup_logger(__name__)

_DURATION_RE = re.compile(r"^(?:(\d+):)?(\d+):(\d{1,2})$")


def _seconds(duration: object) -> int | None:
    """`"0:24"` / `"1:05:09"` → seconds; None if it isn't in that shape."""
    m = _DURATION_RE.match(str(duration or "").strip())
    if not m:
        return None
    h, mins, secs = (int(x or 0) for x in m.groups())
    return h * 3600 + mins * 60 + secs


def _started_at(details: dict, journey: list) -> datetime | None:
    """The runtime's `start_at` is in its server's local time with no zone, so the
    epoch stamps on the journey are the reliable clock; fall back to `start_at` as UTC."""
    stamps = [i["created_at"] for i in journey if isinstance(i, dict) and isinstance(i.get("created_at"), (int, float))]
    if stamps:
        return datetime.fromtimestamp(min(stamps), timezone.utc)
    try:
        return datetime.strptime(str(details.get("start_at")), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _text(v: object) -> str | None:
    return None if v is None or v == "" else str(v)


def summary(c: CallLog) -> CallLogSummary:
    return CallLogSummary(
        id=str(c.id), agent_id=c.agent_id, session_id=c.session_id, source=c.source, direction=c.direction,
        status=c.status, test=c.test, duration=c.duration, duration_seconds=c.duration_seconds,
        started_at=c.started_at, from_phone=c.from_phone, to_phone=c.to_phone, web_uuid=c.web_uuid,
        recording_sid=c.recording_sid, hangup_reason=c.hangup_reason, messages=c.messages, created_at=c.created_at,
    )  # fmt: skip


async def ingest(agent_id: str, call_payload: dict) -> CallLogStored:
    """Stores (or, for a retried session, updates) the call log the voice runtime posted."""
    if not PydanticObjectId.is_valid(agent_id):
        raise NotFoundError("Agent not found")
    agent = await Agent.get(PydanticObjectId(agent_id))
    if agent is None:
        raise NotFoundError("Agent not found")
    interaction = call_payload.get("interaction")
    if not isinstance(interaction, dict):
        raise UnprocessableEntityError("call_payload.interaction is required and must be an object")
    details = interaction.get("details") if isinstance(interaction.get("details"), dict) else {}
    journey = interaction.get("interaction_journey") if isinstance(interaction.get("interaction_journey"), list) else []
    hangup = details.get("hangup_reason")
    fields = {
        "org_id": agent.org_id,
        "session_id": _text(details.get("session_id")),
        "source": _text(interaction.get("source")),
        "direction": _text(interaction.get("direction")),
        "status": _text(interaction.get("status")),
        "test": bool(interaction.get("test")),
        "duration": _text(details.get("duration")),
        "duration_seconds": _seconds(details.get("duration")),
        "started_at": _started_at(details, journey),
        "from_phone": _text(details.get("from_phone")),
        "to_phone": _text(details.get("to_phone")),
        "web_uuid": _text(details.get("web_uuid")),
        "recording_sid": _text(details.get("recording_sid")),
        "hangup_reason": _text(hangup.get("end_reason") if isinstance(hangup, dict) else hangup),
        "messages": sum(1 for i in journey if isinstance(i, dict) and i.get("type") == "message"),
        "interaction": interaction,
    }
    existing = (
        await CallLog.find_one(CallLog.agent_id == agent_id, CallLog.session_id == fields["session_id"])
        if fields["session_id"]
        else None
    )
    if existing is not None:
        for k, v in fields.items():
            setattr(existing, k, v)
        existing.updated_at = datetime.now(timezone.utc)
        await existing.save()
        log, created = existing, False
    else:
        log = CallLog(agent_id=agent_id, **fields)
        await log.insert()
        created = True
    logger.info("call log stored: agent=%s session=%s id=%s created=%s", agent_id, log.session_id, log.id, created)
    return CallLogStored(id=str(log.id), agent_id=agent_id, session_id=log.session_id, created=created)


async def list_logs(
    agent_id: PydanticObjectId, auth: AuthContext, *, q: str | None, status: str | None, source: str | None,
    test: bool | None, skip: int, limit: int,
) -> CallLogListOut:  # fmt: skip
    agent = await agent_service.get_owned_agent(agent_id, auth, write=False)
    query: dict = {"agent_id": str(agent.id)}
    if status:
        query["status"] = status
    if source:
        query["source"] = source
    if test is not None:
        query["test"] = test
    if q and q.strip():
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        query["$or"] = [{"session_id": rx}, {"from_phone": rx}, {"to_phone": rx}, {"web_uuid": rx}]
    total = await CallLog.find(query).count()
    # Newest first; the journey (large) is part of `interaction`, so list rows are built without exposing it.
    rows = await CallLog.find(query).sort("-started_at", "-created_at").skip(skip).limit(limit).to_list()
    return CallLogListOut(items=[summary(c) for c in rows], total=total)


async def get_log(agent_id: PydanticObjectId, log_id: str, auth: AuthContext) -> CallLogOut:
    agent = await agent_service.get_owned_agent(agent_id, auth, write=False)
    if not PydanticObjectId.is_valid(log_id):
        raise NotFoundError("Call log not found")
    c = await CallLog.get(PydanticObjectId(log_id))
    if c is None or c.agent_id != str(agent.id):
        raise NotFoundError("Call log not found")
    return CallLogOut(**summary(c).model_dump(), interaction=c.interaction)

