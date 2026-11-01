import json
import secrets
from datetime import datetime, timezone

from beanie import PydanticObjectId
from common.errors import BadRequestError, ConflictError, NotFoundError, UnprocessableEntityError
from common.log_utils import setup_logger
from google.protobuf.json_format import MessageToDict, ParseDict, ParseError
from livekit import api
from livekit.protocol import sip as lksip

from agents_service.agent_configs import repository as config_repo
from agents_service.agents import service as agent_service
from agents_service.core.config import get_settings
from agents_service.core.deps import AuthContext
from agents_service.telephony.model import TelephonyConnection
from agents_service.telephony.schema import (
    AvailableTrunk,
    DispatchRuleOut,
    TelephonyCall,
    TelephonyCallOut,
    TelephonyConnect,
    TelephonyOut,
    TrunkIn,
    TrunkList,
    TrunkOut,
    TrunkUpdate,
)

logger = setup_logger(__name__)

_TRANSPORT = {
    "auto": lksip.SIPTransport.SIP_TRANSPORT_AUTO,
    "udp": lksip.SIPTransport.SIP_TRANSPORT_UDP,
    "tcp": lksip.SIPTransport.SIP_TRANSPORT_TCP,
    "tls": lksip.SIPTransport.SIP_TRANSPORT_TLS,
}
_TRANSPORT_NAME = {v: k for k, v in _TRANSPORT.items()}


def _lk() -> api.LiveKitAPI:
    s = get_settings()
    if not (s.livekit_url and s.livekit_api_key and s.livekit_api_secret):
        raise BadRequestError("Telephony isn't configured: set LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET")
    return api.LiveKitAPI(url=s.livekit_url, api_key=s.livekit_api_key, api_secret=s.livekit_api_secret)


async def _lk_call(coro):
    """Run one LiveKit call, turning its errors into a 400 the UI can show."""
    try:
        return await coro
    except api.TwirpError as e:
        logger.warning("livekit error: %s %s", e.code, e.message)
        raise BadRequestError(f"LiveKit: {e.message}") from e


# ---------------------------------------------------------------- sharing


async def _linked(trunk_id: str | None, except_agent: str | None = None) -> list[TelephonyConnection]:
    """Agents whose outbound trunk is this one (a trunk may be shared by several agents)."""
    if not trunk_id:
        return []
    q: dict = {"outbound_trunk_id": trunk_id}
    if except_agent:
        q["agent_id"] = {"$ne": except_agent}
    return await TelephonyConnection.find(q).to_list()


def _is_pool_trunk(t) -> bool:
    """Trunks made for an agent by this app carry `agent_id` in their metadata; everything else was created by a
    Super Admin and is the shared pool every organization may link to."""
    try:
        return "agent_id" not in json.loads(t.metadata or "{}")
    except (ValueError, TypeError, AttributeError):
        return True


def _visible_to(t, linked: list[TelephonyConnection], org_id: str | None) -> bool:
    """A pool trunk is open to everyone. A trunk made for an agent is open to the other agents of the same
    organization (so one provider trunk can serve several agents), and never to another organization."""
    return _is_pool_trunk(t) or any(c.org_id == org_id for c in linked)


def _inbound_numbers(conn: TelephonyConnection) -> list[str]:
    """The numbers inbound calls arrive on: a separately entered one, else the outbound numbers."""
    return conn.inbound_numbers or conn.numbers


async def _assert_inbound_numbers_free(numbers: list[str], agent_id: str) -> None:
    """Outbound trunks may share numbers, but a number can answer inbound calls for only one agent."""
    for c in await TelephonyConnection.find({"inbound_enabled": True, "agent_id": {"$ne": agent_id}}).to_list():
        clash = sorted(set(numbers) & set(_inbound_numbers(c)))
        if clash:
            raise ConflictError(f"{', '.join(clash)} already receives inbound calls for another agent")


# ------------------------------------------------------------- serialization


def _out(conn: TelephonyConnection | None) -> TelephonyOut:
    s = get_settings()
    base = {"origination_uri": s.livekit_sip_uri}
    if conn is None:
        return TelephonyOut(connected=False, **base)
    return TelephonyOut(
        connected=True,
        termination_uri=conn.termination_uri,
        auth_username=conn.auth_username,
        numbers=conn.numbers,
        outbound_enabled=conn.outbound_enabled,
        inbound_enabled=conn.inbound_enabled,
        inbound_numbers=_inbound_numbers(conn),
        outbound_trunk_id=conn.outbound_trunk_id,
        outbound_trunk_shared=conn.outbound_trunk_shared,
        inbound_trunk_id=conn.inbound_trunk_id,
        dispatch_rule_id=conn.dispatch_rule_id,
        updated_at=conn.updated_at,
        **base,
    )


async def get(agent_id: PydanticObjectId, auth: AuthContext) -> TelephonyOut:
    await agent_service.get_owned_agent(agent_id, auth, write=False)
    return _out(await TelephonyConnection.find_one(TelephonyConnection.agent_id == str(agent_id)))


# -------------------------------------------------------------------- connect


# Inbound calls always run the live (production) version of the agent; outbound calls choose their
# environment per call (see place_call).
INBOUND_ENVIRONMENT = "production"


def _rule_metadata(agent_id: str) -> str:
    # Read by the voice agent's VoicePipeline.parse_call_metadata (participant metadata).
    return json.dumps({"type": "inbound", "agent_id": agent_id, "environment": INBOUND_ENVIRONMENT})


async def _sync_outbound(lk: api.LiveKitAPI, conn: TelephonyConnection, p: TelephonyConnect, agent_id: str) -> None:
    name = f"bolotext-{agent_id}-outbound"
    if conn.outbound_trunk_id and (conn.outbound_trunk_shared or await _linked(conn.outbound_trunk_id, agent_id)):
        # Other agents use this trunk too; leave it untouched and give this agent its own.
        conn.outbound_trunk_id = None
        conn.outbound_trunk_shared = False
    if conn.outbound_trunk_id:
        await _lk_call(
            lk.sip.update_sip_outbound_trunk_fields(
                conn.outbound_trunk_id,
                name=name,
                address=p.termination_uri,
                numbers=p.numbers,
                transport=_TRANSPORT[p.transport],
                auth_username=p.auth_username or "",
                auth_password=p.auth_password if p.auth_password else None,
            )
        )
        return
    if p.auth_username and not p.auth_password:
        raise BadRequestError("Enter the auth password for this username")
    trunk = lksip.SIPOutboundTrunkInfo(
        name=name,
        address=p.termination_uri,
        numbers=p.numbers,
        transport=_TRANSPORT[p.transport],
        auth_username=p.auth_username or "",
        auth_password=p.auth_password or "",
        metadata=json.dumps({"agent_id": agent_id}),
    )
    created = await _lk_call(lk.sip.create_sip_outbound_trunk(lksip.CreateSIPOutboundTrunkRequest(trunk=trunk)))
    conn.outbound_trunk_id = created.sip_trunk_id


async def _remove_inbound(lk: api.LiveKitAPI, conn: TelephonyConnection) -> None:
    if conn.dispatch_rule_id:
        await _lk_call(lk.sip.delete_sip_dispatch_rule(lksip.DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=conn.dispatch_rule_id)))
        conn.dispatch_rule_id = None
    if conn.inbound_trunk_id:
        await _lk_call(lk.sip.delete_sip_trunk(lksip.DeleteSIPTrunkRequest(sip_trunk_id=conn.inbound_trunk_id)))
        conn.inbound_trunk_id = None


async def _sync_inbound(lk: api.LiveKitAPI, conn: TelephonyConnection, agent_id: str) -> None:
    """Inbound trunk (the saved numbers) + the dispatch rule that sends those calls to this agent."""
    # The dispatch rule is cheap and carries the agent id, so always rebuild it.
    if conn.dispatch_rule_id:
        await _lk_call(lk.sip.delete_sip_dispatch_rule(lksip.DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=conn.dispatch_rule_id)))
        conn.dispatch_rule_id = None
    name = f"bolotext-{agent_id}-inbound"
    if conn.inbound_trunk_id:
        await _lk_call(lk.sip.update_sip_inbound_trunk_fields(conn.inbound_trunk_id, name=name, numbers=_inbound_numbers(conn)))
    else:
        trunk = lksip.SIPInboundTrunkInfo(name=name, numbers=_inbound_numbers(conn), metadata=json.dumps({"agent_id": agent_id}))
        created = await _lk_call(lk.sip.create_sip_inbound_trunk(lksip.CreateSIPInboundTrunkRequest(trunk=trunk)))
        conn.inbound_trunk_id = created.sip_trunk_id
    rule = lksip.SIPDispatchRuleInfo(
        name=name,
        trunk_ids=[conn.inbound_trunk_id],
        rule=lksip.SIPDispatchRule(dispatch_rule_individual=lksip.SIPDispatchRuleIndividual(room_prefix=f"in-{agent_id[-6:]}-")),
        metadata=_rule_metadata(agent_id),
    )
    created_rule = await _lk_call(lk.sip.create_sip_dispatch_rule(lksip.CreateSIPDispatchRuleRequest(dispatch_rule=rule)))
    conn.dispatch_rule_id = created_rule.sip_dispatch_rule_id


async def connect(agent_id: PydanticObjectId, auth: AuthContext, p: TelephonyConnect) -> TelephonyOut:
    agent = await agent_service.get_owned_agent(agent_id, auth, write=True)
    aid = str(agent.id)
    conn = await TelephonyConnection.find_one(TelephonyConnection.agent_id == aid)
    follows = conn is not None and conn.inbound_enabled and not conn.inbound_numbers  # inbound uses the outbound numbers
    if follows:
        await _assert_inbound_numbers_free(p.numbers, aid)
    is_new = conn is None
    if conn is None:
        conn = TelephonyConnection(agent_id=aid, org_id=agent.org_id, termination_uri=p.termination_uri)
    conn.numbers = p.numbers
    async with _lk() as lk:
        await _sync_outbound(lk, conn, p, aid)
        if follows:  # inbound is live on the outbound numbers: keep them in step
            await _sync_inbound(lk, conn, aid)
    conn.termination_uri = p.termination_uri
    conn.auth_username = p.auth_username
    conn.outbound_enabled = True
    conn.updated_at = datetime.now(timezone.utc)
    await conn.insert() if is_new else await conn.save()
    return _out(conn)


def _has_numbers(t) -> bool:
    return bool(t.numbers) and "*" not in t.numbers and "" not in t.numbers


async def list_available_trunks(agent_id: PydanticObjectId, auth: AuthContext) -> list[AvailableTrunk]:
    agent = await agent_service.get_owned_agent(agent_id, auth, write=False)
    aid = str(agent.id)
    by_trunk: dict[str, list[TelephonyConnection]] = {}
    for c in await TelephonyConnection.find_all().to_list():
        if c.outbound_trunk_id:
            by_trunk.setdefault(c.outbound_trunk_id, []).append(c)
    async with _lk() as lk:
        res = await _lk_call(lk.sip.list_sip_outbound_trunk(lksip.ListSIPOutboundTrunkRequest()))
    out = []
    for t in res.items:
        linked = by_trunk.get(t.sip_trunk_id, [])
        if not _visible_to(t, linked, agent.org_id):
            continue
        out.append(
            AvailableTrunk(
                id=t.sip_trunk_id, name=t.name, address=t.address, numbers=list(t.numbers), transport=_TRANSPORT_NAME.get(t.transport),
                linked=any(c.agent_id == aid for c in linked), shared_with=sum(1 for c in linked if c.agent_id != aid), usable=_has_numbers(t),
            )
        )
    return out


async def use_existing_trunk(agent_id: PydanticObjectId, auth: AuthContext, trunk_id: str) -> TelephonyOut:
    """Connects the agent to an existing outbound trunk instead of creating one, even if other agents already use
    it. The trunk's numbers become the agent's numbers; the trunk itself is shared and never edited from here."""
    agent = await agent_service.get_owned_agent(agent_id, auth, write=True)
    aid = str(agent.id)
    async with _lk() as lk:
        res = await _lk_call(lk.sip.list_sip_outbound_trunk(lksip.ListSIPOutboundTrunkRequest(trunk_ids=[trunk_id])))
    trunk = next((t for t in res.items if t.sip_trunk_id == trunk_id), None)
    if trunk is None:
        raise NotFoundError("That trunk doesn't exist any more")
    if not _visible_to(trunk, await _linked(trunk_id), agent.org_id):
        raise BadRequestError("That trunk isn't available to this agent")
    if not _has_numbers(trunk):
        raise BadRequestError("This trunk has no specific phone numbers, so calls can't be tied to this agent. Ask a Super Admin to add the number to the trunk.")

    conn = await TelephonyConnection.find_one(TelephonyConnection.agent_id == aid)
    follows = conn is not None and conn.inbound_enabled and not conn.inbound_numbers
    if follows:
        await _assert_inbound_numbers_free(list(trunk.numbers), aid)  # inbound is live and will move to these numbers
    is_new = conn is None
    if conn is None:
        conn = TelephonyConnection(agent_id=aid, org_id=agent.org_id, termination_uri=trunk.address)
    async with _lk() as lk:
        # Replacing a dedicated trunk of ours that no other agent uses: it is dead weight now, so remove it.
        old = conn.outbound_trunk_id
        if old and old != trunk_id and not conn.outbound_trunk_shared and not await _linked(old, aid):
            await _lk_call(lk.sip.delete_sip_trunk(lksip.DeleteSIPTrunkRequest(sip_trunk_id=old)))
        conn.outbound_trunk_id = trunk_id
        conn.outbound_trunk_shared = True
        conn.termination_uri = trunk.address
        conn.auth_username = trunk.auth_username or None
        conn.numbers = list(trunk.numbers)
        conn.outbound_enabled = True
        if follows:
            await _sync_inbound(lk, conn, aid)
    conn.updated_at = datetime.now(timezone.utc)
    await conn.insert() if is_new else await conn.save()
    return _out(conn)


async def enable_inbound(agent_id: PydanticObjectId, auth: AuthContext, numbers: list[str] | None = None) -> TelephonyOut:
    """Production only: answer calls to the connected numbers with this agent's Production config.
    Needs the provider details saved first (done in Development)."""
    await agent_service.get_owned_agent(agent_id, auth, write=True)
    aid = str(agent_id)
    conn = await TelephonyConnection.find_one(TelephonyConnection.agent_id == aid)
    if conn is None:
        raise BadRequestError("Fill in the telephony details in Development first, then enable inbound here")
    if await config_repo.get_by_agent_id(agent_id, INBOUND_ENVIRONMENT) is None:
        raise BadRequestError("Promote this agent to Production first; inbound calls run its Production config")
    # `numbers` is a different inbound number the user entered after the outbound ones clashed with another agent.
    wanted = ([] if numbers == conn.numbers else numbers) if numbers else conn.inbound_numbers
    await _assert_inbound_numbers_free(wanted or conn.numbers, aid)  # check first: a refusal must change nothing
    conn.inbound_numbers = wanted
    async with _lk() as lk:
        await _sync_inbound(lk, conn, aid)
    conn.inbound_enabled = True
    conn.updated_at = datetime.now(timezone.utc)
    await conn.save()
    return _out(conn)


async def disable_inbound(agent_id: PydanticObjectId, auth: AuthContext) -> TelephonyOut:
    await agent_service.get_owned_agent(agent_id, auth, write=True)
    conn = await TelephonyConnection.find_one(TelephonyConnection.agent_id == str(agent_id))
    if conn is None or not conn.inbound_enabled:
        return _out(conn)
    async with _lk() as lk:
        await _remove_inbound(lk, conn)
    conn.inbound_enabled = False
    conn.updated_at = datetime.now(timezone.utc)
    await conn.save()
    return _out(conn)


async def disconnect(agent_id: PydanticObjectId, auth: AuthContext) -> TelephonyOut:
    await agent_service.get_owned_agent(agent_id, auth, write=True)
    conn = await TelephonyConnection.find_one(TelephonyConnection.agent_id == str(agent_id))
    if conn is None:
        return _out(None)
    async with _lk() as lk:
        if conn.dispatch_rule_id:
            await _lk_call(lk.sip.delete_sip_dispatch_rule(lksip.DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=conn.dispatch_rule_id)))
        in_use_elsewhere = conn.outbound_trunk_shared or bool(await _linked(conn.outbound_trunk_id, str(agent_id)))
        own_outbound = None if in_use_elsewhere else conn.outbound_trunk_id
        for tid in (conn.inbound_trunk_id, own_outbound):
            if tid:
                await _lk_call(lk.sip.delete_sip_trunk(lksip.DeleteSIPTrunkRequest(sip_trunk_id=tid)))
    await conn.delete()
    return _out(None)


# ----------------------------------------------------------------------- call


async def place_call(agent_id: PydanticObjectId, auth: AuthContext, p: TelephonyCall) -> TelephonyCallOut:
    """Starts an outbound call. The SIP participant is created in a fresh room with the agent id and
    environment in its metadata; the (unnamed) voice agent is auto-dispatched into that room, reads the
    metadata to load the right config, and starts talking only once the callee answers
    (bolotext-agent: src/services/outbound_dialer.py)."""
    await agent_service.get_owned_agent(agent_id, auth, write=True)
    aid = str(agent_id)
    conn = await TelephonyConnection.find_one(TelephonyConnection.agent_id == aid)
    if conn is None or not conn.outbound_enabled or not conn.outbound_trunk_id:
        raise BadRequestError("Connect telephony with outbound calling enabled first")
    room = f"out-{aid[-6:]}-{secrets.token_hex(4)}"
    # Read by the voice agent's VoicePipeline.parse_call_metadata (participant metadata).
    metadata = json.dumps(
        {
            "type": "outbound",
            "agent_id": aid,
            "environment": p.environment,
            "test": p.environment != "production",  # Production calls count as real, whoever placed them
            "custom_variables": [{"key": k, "value": v} for k, v in p.custom_variables.items()],
        }
    )
    async with _lk() as lk:
        info = await _lk_call(
            lk.sip.create_sip_participant(
                lksip.CreateSIPParticipantRequest(
                    sip_trunk_id=conn.outbound_trunk_id,
                    sip_call_to=p.phone_number,
                    room_name=room,
                    participant_identity=f"sip_{p.phone_number}",
                    participant_name=p.phone_number,
                    participant_metadata=metadata,
                    # Return as soon as dialing starts instead of holding this request until the callee
                    # picks up; the agent waits for the answer itself.
                    wait_until_answered=False,
                    krisp_enabled=True,
                )
            )
        )
    logger.info("outbound call started agent=%s room=%s env=%s", aid, room, p.environment)
    return TelephonyCallOut(room_name=room, sip_call_id=info.sip_call_id)


# ------------------------------------------------- Super Admin: trunk CRUD


async def _agent_map() -> dict[str, str]:
    m: dict[str, str] = {}
    for c in await TelephonyConnection.find_all().to_list():
        for tid in (c.outbound_trunk_id, c.inbound_trunk_id, c.dispatch_rule_id):
            if tid:
                m[tid] = c.agent_id
    return m


def _outbound_out(t, owners: dict[str, str]) -> TrunkOut:
    return TrunkOut(
        id=t.sip_trunk_id, kind="outbound", name=t.name, address=t.address, numbers=list(t.numbers), auth_username=t.auth_username or None,
        transport=_TRANSPORT_NAME.get(t.transport), agent_id=owners.get(t.sip_trunk_id),
    )


def _inbound_out(t, owners: dict[str, str]) -> TrunkOut:
    return TrunkOut(
        id=t.sip_trunk_id, kind="inbound", name=t.name, numbers=list(t.numbers), auth_username=t.auth_username or None,
        allowed_addresses=list(t.allowed_addresses), agent_id=owners.get(t.sip_trunk_id),
    )


async def list_trunks() -> TrunkList:
    owners = await _agent_map()
    async with _lk() as lk:
        out = await _lk_call(lk.sip.list_sip_outbound_trunk(lksip.ListSIPOutboundTrunkRequest()))
        inn = await _lk_call(lk.sip.list_sip_inbound_trunk(lksip.ListSIPInboundTrunkRequest()))
        rules = await _lk_call(lk.sip.list_sip_dispatch_rule(lksip.ListSIPDispatchRuleRequest()))
    return TrunkList(
        origination_uri=get_settings().livekit_sip_uri,
        outbound=[_outbound_out(t, owners) for t in out.items],
        inbound=[_inbound_out(t, owners) for t in inn.items],
        dispatch_rules=[
            DispatchRuleOut(
                id=r.sip_dispatch_rule_id, name=r.name, trunk_ids=list(r.trunk_ids), metadata=r.metadata or None,
                room_prefix=r.rule.dispatch_rule_individual.room_prefix or None, agent_id=owners.get(r.sip_dispatch_rule_id),
            )
            for r in rules.items
        ],
    )


async def create_trunk(kind: str, p: TrunkIn) -> TrunkOut:
    if kind == "outbound":
        if not p.address:
            raise BadRequestError("An outbound trunk needs the provider's SIP address")
        if p.auth_username and not p.auth_password:
            raise BadRequestError("Enter the auth password for this username")
        trunk = lksip.SIPOutboundTrunkInfo(
            name=p.name, address=p.address, numbers=p.numbers, transport=_TRANSPORT[p.transport],
            auth_username=p.auth_username or "", auth_password=p.auth_password or "",
        )
        async with _lk() as lk:
            t = await _lk_call(lk.sip.create_sip_outbound_trunk(lksip.CreateSIPOutboundTrunkRequest(trunk=trunk)))
        return _outbound_out(t, {})
    trunk = lksip.SIPInboundTrunkInfo(
        name=p.name, numbers=p.numbers, allowed_addresses=p.allowed_addresses,
        auth_username=p.auth_username or "", auth_password=p.auth_password or "",
    )
    async with _lk() as lk:
        t = await _lk_call(lk.sip.create_sip_inbound_trunk(lksip.CreateSIPInboundTrunkRequest(trunk=trunk)))
    return _inbound_out(t, {})


async def update_trunk(kind: str, trunk_id: str, p: TrunkUpdate) -> TrunkOut:
    async with _lk() as lk:
        if kind == "outbound":
            t = await _lk_call(
                lk.sip.update_sip_outbound_trunk_fields(
                    trunk_id, name=p.name, address=p.address, numbers=p.numbers, auth_username=p.auth_username,
                    auth_password=p.auth_password or None, transport=_TRANSPORT[p.transport] if p.transport else None,
                )
            )
            return _outbound_out(t, await _agent_map())
        t = await _lk_call(
            lk.sip.update_sip_inbound_trunk_fields(
                trunk_id, name=p.name, numbers=p.numbers, allowed_addresses=p.allowed_addresses,
                auth_username=p.auth_username, auth_password=p.auth_password or None,
            )
        )
        return _inbound_out(t, await _agent_map())


_RAW_READONLY = ("sipTrunkId", "sip_trunk_id", "createdAt", "created_at", "updatedAt", "updated_at")


async def _get_trunk_info(lk: api.LiveKitAPI, kind: str, trunk_id: str):
    if kind == "outbound":
        res = await _lk_call(lk.sip.list_sip_outbound_trunk(lksip.ListSIPOutboundTrunkRequest(trunk_ids=[trunk_id])))
    else:
        res = await _lk_call(lk.sip.list_sip_inbound_trunk(lksip.ListSIPInboundTrunkRequest(trunk_ids=[trunk_id])))
    info = next((t for t in res.items if t.sip_trunk_id == trunk_id), None)
    if info is None:
        raise NotFoundError("Trunk not found")
    return info


async def get_trunk_raw(kind: str, trunk_id: str) -> dict:
    """The trunk as LiveKit JSON for the JSON editor: every field, including empty/default ones and the read-only
    id and timestamps (ignored on save), but never the password."""
    async with _lk() as lk:
        info = await _get_trunk_info(lk, kind, trunk_id)
    doc = MessageToDict(info, always_print_fields_with_no_presence=True)
    doc.pop("authPassword", None)
    return doc


async def replace_trunk_raw(kind: str, trunk_id: str, doc: dict) -> TrunkOut:
    """Replaces the trunk with the edited JSON. Anything omitted from the JSON is cleared (LiveKit replace
    semantics), except the password: it is not shown in the editor, so when `authPassword` is absent the saved one is kept."""
    info_cls = lksip.SIPOutboundTrunkInfo if kind == "outbound" else lksip.SIPInboundTrunkInfo
    try:
        info = ParseDict({k: v for k, v in doc.items() if k not in _RAW_READONLY}, info_cls())
    except ParseError as e:
        raise UnprocessableEntityError(str(e).splitlines()[0]) from e
    if not info.name:
        raise UnprocessableEntityError('"name" is required')
    async with _lk() as lk:
        existing = await _get_trunk_info(lk, kind, trunk_id)
        if not info.auth_password:
            info.auth_password = existing.auth_password
            if info.auth_username and not info.auth_password:
                # LiveKit may not return the stored password, and a replace without it would wipe it.
                raise BadRequestError('Add "authPassword" to the JSON: the saved password can\'t be read back, and saving without it would clear it')
        info.sip_trunk_id = trunk_id
        if kind == "outbound":
            saved = await _lk_call(lk.sip.update_sip_outbound_trunk(trunk_id, info))
            return _outbound_out(saved, await _agent_map())
        saved = await _lk_call(lk.sip.update_sip_inbound_trunk(trunk_id, info))
        return _inbound_out(saved, await _agent_map())


async def delete_trunk(kind: str, trunk_id: str) -> None:
    async with _lk() as lk:
        if kind == "dispatch-rule":
            await _lk_call(lk.sip.delete_sip_dispatch_rule(lksip.DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=trunk_id)))
        else:
            await _lk_call(lk.sip.delete_sip_trunk(lksip.DeleteSIPTrunkRequest(sip_trunk_id=trunk_id)))
    # Forget it on every agent that used it so a stale id isn't reused.
    for conn in await TelephonyConnection.find({"$or": [{"outbound_trunk_id": trunk_id}, {"inbound_trunk_id": trunk_id}, {"dispatch_rule_id": trunk_id}]}).to_list():
        for f in ("outbound_trunk_id", "inbound_trunk_id", "dispatch_rule_id"):
            if getattr(conn, f) == trunk_id:
                setattr(conn, f, None)
        await conn.save()
