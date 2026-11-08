import re
from datetime import datetime, timezone

from beanie import PydanticObjectId
from common.errors import NotFoundError, UnprocessableEntityError
from common.log_utils import setup_logger

from agents_service.agents import service as agent_service
from agents_service.agents.model import Agent
from agents_service.call_logs.model import CallLog
from agents_service.usage import service as usage_service
from agents_service.call_logs.schema import CallUsageIn, CallLogIn, CallLogListOut, CallLogOut, CallLogStored, CallLogSummary
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


def started_at(doc: dict) -> datetime | None:
    """The runtime's `callStartTime` is in its server's local time with no zone, so the
    epoch stamps on the conversation log are the reliable clock; fall back to it as UTC."""
    log = doc.get("conversation_log") if isinstance(doc.get("conversation_log"), list) else []
    stamps = [i["created_at"] for i in log if isinstance(i, dict) and isinstance(i.get("created_at"), (int, float))]
    if stamps:
        return datetime.fromtimestamp(min(stamps), timezone.utc)
    try:
        return datetime.strptime(str(doc.get("callStartTime")), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _text(v: object) -> str | None:
    return None if v is None or v == "" else str(v)


def _lower(v: object) -> str | None:
    t = _text(v)
    return t.lower() if t else None


def summary(c: CallLog) -> CallLogSummary:
    """The list-row view, derived from the stored document on read."""
    d = c.model_dump()
    log = d.get("conversation_log") if isinstance(d.get("conversation_log"), list) else []
    hangup = d.get("hangup_reason")
    return CallLogSummary(
        id=str(c.id), agent_id=c.bot_id, session_id=c.conversation_id, source=_text(d.get("source")),
        direction=_lower(d.get("callType")), status=_lower(d.get("call_status")), test=bool(d.get("is_test")),
        duration=_text(d.get("duration")), duration_seconds=_seconds(d.get("duration")), started_at=started_at(d),
        from_phone=_text(d.get("from_phone")), to_phone=_text(d.get("to_phone")), web_uuid=_text(d.get("web_uuid")),
        recording_sid=_text(d.get("recording_sid")),
        hangup_reason=_text(hangup.get("end_reason") if isinstance(hangup, dict) else hangup),
        messages=sum(1 for i in log if isinstance(i, dict) and i.get("type") == "message"),
        created_at=c.created_at,
    )  # fmt: skip


async def ingest(payload: CallLogIn) -> CallLogStored:
    """Stores (or, for a retried conversation, replaces) the call log the voice runtime posted.
    The document is saved as received; the only thing added is the agent's `org_id` for tenant scoping."""
    if not PydanticObjectId.is_valid(payload.bot_id):
        raise NotFoundError("Agent not found")
    agent = await Agent.get(PydanticObjectId(payload.bot_id))
    if agent is None:
        raise NotFoundError("Agent not found")
    fields = {k: v for k, v in payload.model_dump().items() if k not in ("_id", "id", "org_id")}  # ids are ours to assign
    existing = (
        await CallLog.find_one(CallLog.bot_id == payload.bot_id, CallLog.conversation_id == payload.conversation_id)
        if payload.conversation_id
        else None
    )
    if existing is not None:
        for k, v in {**fields, "org_id": agent.org_id}.items():
            setattr(existing, k, v)
        existing.updated_at = datetime.now(timezone.utc)
        await existing.save()
        log, created = existing, False
    else:
        log = CallLog(org_id=agent.org_id, **fields)
        await log.insert()
        created = True
    logger.info("call log stored: agent=%s conversation=%s id=%s created=%s", log.bot_id, log.conversation_id, log.id, created)
    return CallLogStored(id=str(log.id), agent_id=log.bot_id, session_id=log.conversation_id, created=created)


async def record_usage(payload: CallUsageIn) -> None:
    """Adds one call to the usage rollup. Triggered by the voice runtime, not by log ingest."""
    if not PydanticObjectId.is_valid(payload.bot_id):
        raise NotFoundError("Agent not found")
    agent = await Agent.get(PydanticObjectId(payload.bot_id))
    if agent is None:
        raise NotFoundError("Agent not found")
    when = datetime.strptime(payload.day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    doc = {"token_usage": payload.token_usage, "models": payload.models, "environment": payload.environment, "is_test": payload.is_test}
    await usage_service.apply(await usage_service.contributions(agent.org_id, payload.bot_id, doc, when), 1)


async def list_logs(
    agent_id: PydanticObjectId, auth: AuthContext, *, q: str | None, status: str | None, source: str | None,
    test: bool | None, skip: int, limit: int,
) -> CallLogListOut:  # fmt: skip
    agent = await agent_service.get_owned_agent(agent_id, auth, write=False)
    query: dict = {"bot_id": str(agent.id)}
    if status:
        query["call_status"] = status.upper()
    if source:
        query["source"] = source
    if test is not None:
        query["is_test"] = test
    if q and q.strip():
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        query["$or"] = [{"conversation_id": rx}, {"from_phone": rx}, {"to_phone": rx}, {"web_uuid": rx}]
    total = await CallLog.find(query).count()
    # Newest first; the conversation (large) is only in the stored document, so list rows never expose it.
    rows = await CallLog.find(query).sort("-callStartTime", "-created_at").skip(skip).limit(limit).to_list()
    return CallLogListOut(items=[summary(c) for c in rows], total=total)


async def get_log(agent_id: PydanticObjectId, log_id: str, auth: AuthContext) -> CallLogOut:
    agent = await agent_service.get_owned_agent(agent_id, auth, write=False)
    if not PydanticObjectId.is_valid(log_id):
        raise NotFoundError("Call log not found")
    c = await CallLog.get(PydanticObjectId(log_id))
    if c is None or c.bot_id != str(agent.id):
        raise NotFoundError("Call log not found")
    return CallLogOut(**summary(c).model_dump(), log=c.model_dump(mode="json", exclude={"id", "revision_id"}))

