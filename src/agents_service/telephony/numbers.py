"""LiveKit Phone Numbers: rent a US number and connect it to an agent. No SIP trunk, username or password is involved:
a rented number just needs a dispatch rule (https://docs.livekit.io/telephony/start/phone-numbers/). LiveKit's SDK has no
wrapper for this API yet, so the Twirp endpoints are called directly
(https://docs.livekit.io/reference/telephony/phone-numbers-api/)."""
import json
from datetime import datetime, timezone

import httpx
from common.errors import BadRequestError, ConflictError, NotFoundError
from common.log_utils import setup_logger
from livekit import api
from livekit.protocol import sip as lksip
from users_service.organizations.model import Organization

from agents_service.agent_configs import repository as config_repo
from agents_service.agents import service as agent_service
from agents_service.core.config import get_settings
from agents_service.core.deps import AuthContext
from agents_service.telephony.model import RentedNumber
from agents_service.telephony.schema import NumberSearchResult, RentedNumberList, RentedNumberOut
from agents_service.telephony.service import INBOUND_ENVIRONMENT, _lk, _lk_call, _rule_metadata, _scope

logger = setup_logger(__name__)

_SERVICE = "livekit.PhoneNumberService"
_STATUS = {0: "unknown", 1: "active", 2: "pending", 3: "released", 4: "offline"}
_TYPE = {0: "unknown", 1: "mobile", 2: "local", 3: "toll_free"}
_transport: httpx.AsyncBaseTransport | None = None  # tests swap this for a mock


# ----------------------------------------------------------------- Twirp client


def _token() -> str:
    s = get_settings()
    return api.AccessToken(s.livekit_api_key, s.livekit_api_secret).with_grants(api.VideoGrants()).with_sip_grants(api.SIPGrants(admin=True)).to_jwt()


async def _twirp(method: str, body: dict) -> dict:
    s = get_settings()
    if not (s.livekit_url and s.livekit_api_key and s.livekit_api_secret):
        raise BadRequestError("Phone numbers aren't configured: set LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET")
    base = s.livekit_url.replace("wss://", "https://").replace("ws://", "http://").rstrip("/")
    try:
        async with httpx.AsyncClient(transport=_transport, timeout=20) as c:
            r = await c.post(
                f"{base}/twirp/{_SERVICE}/{method}",
                json=body,
                headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"},
            )
    except httpx.HTTPError as e:
        raise BadRequestError(f"LiveKit is unreachable: {e}") from e
    try:
        data = r.json()
    except ValueError:
        data = {}
    if r.status_code >= 400:
        # Twirp errors are {"code": "...", "msg": "..."}.
        logger.warning("livekit phone numbers %s failed: %s %s", method, r.status_code, data)
        raise BadRequestError(f"LiveKit: {data.get('msg') or data.get('message') or f'HTTP {r.status_code}'}")
    return data


def _g(d: dict, *keys, default=None):
    """First present key: Twirp JSON may use camelCase or the proto's snake_case."""
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _enum(v, table: dict[int, str], prefix: str) -> str:
    if isinstance(v, int):
        return table.get(v, "unknown")
    return str(v or "").removeprefix(prefix).lower() or "unknown"


def _normalize(d: dict) -> dict:
    return {
        "id": _g(d, "id", default=""),
        "phone_number": _g(d, "e164Format", "e164_format", default=""),
        "country_code": _g(d, "countryCode", "country_code"),
        "area_code": _g(d, "areaCode", "area_code"),
        "number_type": _enum(_g(d, "numberType", "number_type"), _TYPE, "PHONE_NUMBER_TYPE_"),
        "locality": _g(d, "locality"),
        "region": _g(d, "region"),
        "capabilities": list(_g(d, "capabilities", default=[])),
        "status": _enum(_g(d, "status"), _STATUS, "PHONE_NUMBER_STATUS_"),
        "dispatch_rule_ids": list(_g(d, "sipDispatchRuleIds", "sip_dispatch_rule_ids", default=[])) or [r for r in [_g(d, "sipDispatchRuleId", "sip_dispatch_rule_id")] if r],
    }


# ---------------------------------------------------------------------- search


async def search(country_code: str, area_code: str | None, limit: int) -> list[NumberSearchResult]:
    body: dict = {"country_code": country_code, "limit": limit}
    if area_code:
        body["area_code"] = area_code
    res = await _twirp("SearchPhoneNumbers", body)
    out = []
    for item in _g(res, "items", default=[]):
        n = _normalize(item)
        out.append(NumberSearchResult(**{k: n[k] for k in ("phone_number", "country_code", "area_code", "number_type", "locality", "region", "capabilities")}))
    return out


# ---------------------------------------------------------------------- helpers


async def _org_names(org_ids: set[str]) -> dict[str, str]:
    from beanie import PydanticObjectId

    ids = [PydanticObjectId(o) for o in org_ids if o and PydanticObjectId.is_valid(o)]
    return {str(o.id): o.name for o in await Organization.find({"_id": {"$in": ids}}).to_list()} if ids else {}


def _out(n: dict, doc: RentedNumber | None, org_names: dict[str, str], warning: str | None = None) -> RentedNumberOut:
    return RentedNumberOut(
        id=n["id"], phone_number=n["phone_number"], number_type=n["number_type"], locality=n["locality"], region=n["region"],
        status=n["status"], agent_id=doc.agent_id if doc else None, org_id=doc.org_id if doc else None,
        org_name=org_names.get(doc.org_id) if doc and doc.org_id else None, external=doc is None, warning=warning,
        dispatch_rule_ids=n.get("dispatch_rule_ids", []),
    )


async def _get_doc(auth: AuthContext, number_id: str) -> RentedNumber:
    """404 unless the number was rented here and, for an Admin, by their own organization."""
    doc = await RentedNumber.find_one(RentedNumber.livekit_id == number_id)
    scope = _scope(auth)
    if doc is None or (scope is not None and doc.org_id != scope):
        raise NotFoundError("Number not found")
    return doc


async def _remove_rule(doc: RentedNumber) -> None:
    if doc.dispatch_rule_id:
        async with _lk() as lk:
            await _lk_call(lk.sip.delete_sip_dispatch_rule(lksip.DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=doc.dispatch_rule_id)))
        doc.dispatch_rule_id = None


async def _connect(auth: AuthContext, doc: RentedNumber, agent_id: str | None) -> None:
    """Points the number at one agent (or at none). Replaces our previous dispatch rule for it."""
    if agent_id is None:
        await _remove_rule(doc)
        doc.agent_id = None
        return
    agent = await agent_service.get_owned_agent(agent_id, auth, write=True)  # type: ignore[arg-type]
    aid = str(agent.id)
    if doc.org_id is not None and agent.org_id != doc.org_id:
        raise BadRequestError("That agent belongs to a different organization than this number")
    if await config_repo.get_by_agent_id(agent.id, INBOUND_ENVIRONMENT) is None:
        raise BadRequestError("Promote this agent to Production first; inbound calls run its Production config")
    await _remove_rule(doc)
    rule = lksip.SIPDispatchRuleInfo(
        name=f"bolotext-number-{doc.phone_number.lstrip('+')}",
        trunk_ids=[],  # a rented number has no trunk; the rule is tied to it through UpdatePhoneNumber below
        rule=lksip.SIPDispatchRule(dispatch_rule_individual=lksip.SIPDispatchRuleIndividual(room_prefix=f"in-{aid[-6:]}-")),
        metadata=_rule_metadata(aid),
    )
    async with _lk() as lk:
        created = await _lk_call(lk.sip.create_sip_dispatch_rule(lksip.CreateSIPDispatchRuleRequest(dispatch_rule=rule)))
    try:
        await _twirp("UpdatePhoneNumber", {"id": doc.livekit_id, "sip_dispatch_rule_id": created.sip_dispatch_rule_id})
    except Exception:
        async with _lk() as lk:  # don't leave a rule that no number points at
            await _lk_call(lk.sip.delete_sip_dispatch_rule(lksip.DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=created.sip_dispatch_rule_id)))
        raise
    doc.dispatch_rule_id = created.sip_dispatch_rule_id
    doc.agent_id = aid
    doc.org_id = doc.org_id or agent.org_id


# ------------------------------------------------------------------------ list


async def list_numbers(auth: AuthContext) -> RentedNumberList:
    scope = _scope(auth)
    res = await _twirp("ListPhoneNumbers", {"limit": 1000})
    live = {n["id"]: n for n in (_normalize(i) for i in _g(res, "items", default=[]))}
    docs = {d.livekit_id: d for d in await RentedNumber.find_all().to_list()}
    names = await _org_names({d.org_id for d in docs.values() if d.org_id})
    items = []
    for nid, n in live.items():
        if n["status"] == "released":
            continue
        doc = docs.get(nid)
        if scope is not None and (doc is None or doc.org_id != scope):
            continue  # an Admin never sees other organizations' numbers, or ones rented outside the app
        items.append(_out(n, doc, names))
    items.sort(key=lambda x: x.phone_number)
    return RentedNumberList(items=items, limit_per_org=None if scope is None else get_settings().phone_numbers_max_per_org)


# ------------------------------------------------------------------------ rent


async def rent(auth: AuthContext, phone_number: str, agent_id: str | None) -> RentedNumberOut:
    scope = _scope(auth)
    if await RentedNumber.find_one(RentedNumber.phone_number == phone_number):
        raise ConflictError("That number is already rented")
    cap = get_settings().phone_numbers_max_per_org
    if scope is not None and len(await RentedNumber.find(RentedNumber.org_id == scope).to_list()) >= cap:
        raise BadRequestError(f"Your organization can rent up to {cap} numbers. Release one first, or ask a Super Admin.")
    if agent_id is not None:  # fail before spending money, not after
        agent = await agent_service.get_owned_agent(agent_id, auth, write=True)  # type: ignore[arg-type]
        if scope is not None and agent.org_id != scope:
            raise BadRequestError("That agent belongs to a different organization")
        if await config_repo.get_by_agent_id(agent.id, INBOUND_ENVIRONMENT) is None:
            raise BadRequestError("Promote this agent to Production first; inbound calls run its Production config")

    res = await _twirp("PurchasePhoneNumber", {"phone_numbers": [phone_number]})
    bought = next(iter(_g(res, "phoneNumbers", "phone_numbers", default=[])), None)
    if not bought:
        raise BadRequestError("LiveKit didn't rent that number (it may have just been taken). Search again.")
    n = _normalize(bought)
    n["phone_number"] = n["phone_number"] or phone_number
    doc = RentedNumber(livekit_id=n["id"], phone_number=n["phone_number"], org_id=scope, created_by=auth.user_id)
    await doc.insert()  # recorded straight away: the number is billed whatever happens next
    warning = None
    if agent_id is not None:
        try:
            await _connect(auth, doc, agent_id)
        except Exception as e:  # noqa: BLE001
            warning = f"The number was rented, but connecting it to the agent failed: {getattr(e, 'message', e)}. Connect it from the list."
    doc.updated_at = datetime.now(timezone.utc)
    await doc.save()
    return _out(n, doc, await _org_names({doc.org_id} if doc.org_id else set()), warning)


# ---------------------------------------------------------------- connect / release


async def _adopt(auth: AuthContext, number_id: str) -> RentedNumber:
    """A number that already existed in LiveKit (rented outside this app) becomes tracked here, unowned until it is
    connected to an agent. Only a Super Admin may do this: an Admin can't tell which organization a loose number is for."""
    res = await _twirp("GetPhoneNumber", {"id": number_id})
    n = _normalize(_g(res, "phoneNumber", "phone_number", default={}))
    if not n["id"] or n["status"] == "released":
        raise NotFoundError("Number not found")
    doc = RentedNumber(livekit_id=n["id"], phone_number=n["phone_number"], org_id=None, created_by=auth.user_id)
    await doc.insert()
    return doc


async def assign(auth: AuthContext, number_id: str, agent_id: str | None) -> RentedNumberOut:
    doc = await RentedNumber.find_one(RentedNumber.livekit_id == number_id)
    if doc is None and _scope(auth) is None:
        doc = await _adopt(auth, number_id)
    elif doc is None:
        raise NotFoundError("Number not found")
    else:
        doc = await _get_doc(auth, number_id)
    await _connect(auth, doc, agent_id)
    doc.updated_at = datetime.now(timezone.utc)
    await doc.save()
    res = await _twirp("GetPhoneNumber", {"id": doc.livekit_id})
    n = _normalize(_g(res, "phoneNumber", "phone_number", default={"id": doc.livekit_id, "e164Format": doc.phone_number}))
    return _out(n, doc, await _org_names({doc.org_id} if doc.org_id else set()))


async def release(auth: AuthContext, number_id: str) -> None:
    """Gives the number back to LiveKit. It is billed through the end of the month either way."""
    scope = _scope(auth)
    doc = await RentedNumber.find_one(RentedNumber.livekit_id == number_id)
    if doc is None and scope is not None:
        raise NotFoundError("Number not found")  # an Admin can only release numbers their own org rented here
    if doc is not None and scope is not None and doc.org_id != scope:
        raise NotFoundError("Number not found")
    await _twirp("ReleasePhoneNumbers", {"ids": [number_id]})
    if doc is not None:
        await _remove_rule(doc)
        await doc.delete()
