import inspect
from datetime import datetime, timezone

from beanie import PydanticObjectId
from common.errors import NotFoundError
from common.log_utils import setup_logger
from users_service.organizations.model import Organization

from agents_service.agent_configs import repository as config_repo
from agents_service.usage.model import ModelPrice, UsageRollup, UsageSettings
from agents_service.usage.schema import (
    CostLine,
    DailyPoint,
    KindSummary,
    ModelPriceIn,
    ModelPriceOut,
    OrgUsageDetail,
    OrgUsageRow,
    PricingList,
    UsageSettingsOut,
    Totals,
    UsageOverview,
    UsageSummary,
)

logger = setup_logger(__name__)

KINDS = ("stt", "llm", "tts")
_SUM_FIELDS = ("calls", "input_tokens", "cached_tokens", "output_tokens", "audio_seconds", "characters")


# ---------------------------------------------------------------- ingest side


def _int(v: object) -> int:
    return int(v) if isinstance(v, (int, float)) and v > 0 else 0


async def _models(agent_id: str, doc: dict) -> dict[str, tuple[str, str]]:
    """provider/model per kind. The voice runtime reports what it actually ran
    (`models`); the current runtime doesn't, so fall back to the agent's
    saved config for the call's environment."""
    reported = doc.get("models") if isinstance(doc.get("models"), dict) else {}
    out: dict[str, tuple[str, str]] = {}
    missing = [k for k in KINDS if not (isinstance(reported.get(k), dict) and reported[k].get("provider_id"))]
    for k in KINDS:
        if k not in missing:
            out[k] = (str(reported[k]["provider_id"]), str(reported[k].get("model_id") or "unknown"))
    if missing and PydanticObjectId.is_valid(agent_id):
        env = doc.get("environment") or ("development" if doc.get("is_test") else "production")
        config = await config_repo.get_by_agent_id(PydanticObjectId(agent_id), env if env in ("development", "stage", "production") else "production")
        if config is not None:
            fallback = {
                "stt": (config.transcriber.provider_id, config.transcriber.model_id),
                "llm": (config.llm.provider_id, config.llm.model_id),
                "tts": (config.voice_persona.provider_id, config.voice_persona.model_id),
            }
            for k in missing:
                p, m = fallback[k]
                out[k] = (p or "unknown", m or "unknown")
    for k in KINDS:
        out.setdefault(k, ("unknown", "unknown"))
    return out


async def contributions(org_id: str | None, agent_id: str, doc: dict, when: datetime | None) -> list[tuple[dict, dict]]:
    """[(key, increments)] for one stored call-log document; stages the call never used are left out."""
    if not org_id:
        return []
    usage = doc.get("token_usage") if isinstance(doc.get("token_usage"), dict) else {}
    amounts = {
        "llm": {
            "input_tokens": _int(usage.get("llm_input_token")),
            "cached_tokens": _int(usage.get("llm_prompt_cached_tokens")),
            "output_tokens": _int(usage.get("llm_output_token")),
        },
        "stt": {"audio_seconds": _int(usage.get("stt_audio_duration"))},
        "tts": {"characters": _int(usage.get("tts_characters_count"))},
    }
    models = await _models(agent_id, doc)
    day = (when or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%d")
    out = []
    for kind, inc in amounts.items():
        if not any(inc.values()):
            continue
        provider, model = models[kind]
        key = {
            "org_id": org_id,
            "day": day,
            "kind": kind,
            "provider_id": provider,
            "model_id": model,
            "test": bool(doc.get("is_test")),
        }
        out.append((key, {**inc, "calls": 1}))
    return out


async def apply(contribs: list[tuple[dict, dict]], sign: int = 1) -> None:
    """`$inc` each rollup document (upsert); sign=-1 backs a previous call out."""
    coll = UsageRollup.get_pymongo_collection()
    now = datetime.now(timezone.utc)
    for key, inc in contribs:
        await coll.update_one(
            key,
            {"$inc": {f: v * sign for f, v in inc.items()}, "$set": {"updated_at": now}},
            upsert=True,
        )


_KEEP_KEYS = (
    ["org_id", "day", "kind", "provider_id", "model_id", "test"],
    ["day", "org_id"],
)


async def drop_stale_indexes() -> None:
    """Earlier shapes of this collection were keyed on agent_id, or without a day. Their unique
    indexes would reject a valid rollup (e.g. a second day), so drop any index that isn't current.
    Safe to run on every start: a fresh DB has nothing to drop."""
    try:
        coll = UsageRollup.get_pymongo_collection()
        info = coll.index_information()
        info = await info if inspect.isawaitable(info) else info
        for name, spec in info.items():
            if name != "_id_" and [f for f, _ in spec["key"]] not in _KEEP_KEYS:
                res = coll.drop_index(name)
                if inspect.isawaitable(res):
                    await res
                logger.warning("dropped stale token_usage index %s", name)
    except Exception:
        logger.exception("could not check token_usage indexes")


async def rebuild_from_call_logs() -> int:
    """Recompute the whole collection from stored call logs. Call-log ingest does not touch
    this collection (the runtime reports usage separately), so `backfill-usage` repairs drift."""
    from agents_service.call_logs.model import CallLog
    from agents_service.call_logs.service import started_at

    coll = UsageRollup.get_pymongo_collection()
    await coll.delete_many({})
    await drop_stale_indexes()
    n = 0
    async for log in CallLog.find_all():
        doc = log.model_dump()
        await apply(await contributions(log.org_id, log.bot_id, doc, started_at(doc) or log.created_at), 1)
        n += 1
    return n


# ----------------------------------------------------------------- read side


async def get_rate() -> float | None:
    doc = await UsageSettings.find_one(UsageSettings.key == "default")
    return doc.usd_to_inr if doc else None


async def set_rate(rate: float) -> UsageSettingsOut:
    doc = await UsageSettings.find_one(UsageSettings.key == "default")
    if doc is None:
        doc = UsageSettings(usd_to_inr=rate)
        await doc.insert()
    else:
        doc.usd_to_inr = rate
        doc.updated_at = datetime.now(timezone.utc)
        await doc.save()
    return UsageSettingsOut(usd_to_inr=doc.usd_to_inr)


def _cost(kind: str, u: dict, price: ModelPrice | None) -> float | None:
    if price is None:
        return None
    if kind == "llm":
        if price.input_per_million is None and price.output_per_million is None:
            return None
        cached = min(u["cached_tokens"], u["input_tokens"])
        cached_rate = price.cached_input_per_million if price.cached_input_per_million is not None else price.input_per_million
        return (
            (u["input_tokens"] - cached) * (price.input_per_million or 0)
            + cached * (cached_rate or 0)
            + u["output_tokens"] * (price.output_per_million or 0)
        ) / 1_000_000
    if kind == "stt":
        return None if price.per_minute is None else u["audio_seconds"] / 60 * price.per_minute
    if price.per_million_chars is None:
        return None
    return u["characters"] / 1_000_000 * price.per_million_chars


def _match(day_from: str | None, day_to: str | None, include_test: bool, **extra) -> dict:
    m: dict = dict(extra)
    if day_from or day_to:
        m["day"] = {**({"$gte": day_from} if day_from else {}), **({"$lte": day_to} if day_to else {})}
    if not include_test:
        m["test"] = False
    return m


def _group_stage(by: list[str]) -> list[dict]:
    return [
        {"$group": {"_id": {f: f"${f}" for f in by}, **{f: {"$sum": f"${f}"} for f in _SUM_FIELDS}}},
    ]


async def _run(pipeline: list[dict]) -> list[dict]:
    # With a Motor client aggregate() returns the cursor directly; with native async pymongo it is a
    # coroutine that resolves to the cursor. Handle both so a client swap doesn't break this.
    cursor = UsageRollup.get_pymongo_collection().aggregate(pipeline)
    if inspect.isawaitable(cursor):
        cursor = await cursor
    return await cursor.to_list(None)


async def _aggregate(match: dict, by: list[str]) -> list[dict]:
    rows = await _run([{"$match": match}, *_group_stage(by)])
    return [{**r["_id"], **{f: r[f] for f in _SUM_FIELDS}} for r in rows]


async def _prices() -> dict[tuple[str, str, str], ModelPrice]:
    return {(p.kind, p.provider_id, p.model_id): p for p in await ModelPrice.find_all().to_list()}


def _summarize(rows: list[dict], prices: dict) -> UsageSummary:
    """rows are (kind, provider, model)-level; collapse into per-kind totals + cost."""
    by_kind: dict[str, dict] = {k: {"u": dict.fromkeys(_SUM_FIELDS, 0), "cost": 0.0, "unpriced": set()} for k in KINDS}
    for r in rows:
        slot = by_kind[r["kind"]]
        for f in _SUM_FIELDS:
            slot["u"][f] += r[f]
        c = _cost(r["kind"], r, prices.get((r["kind"], r["provider_id"], r["model_id"])))
        if c is None:
            slot["unpriced"].add((r["provider_id"], r["model_id"]))
        else:
            slot["cost"] += c
    kinds = [
        KindSummary(kind=k, usage=Totals(**v["u"]), cost=round(v["cost"], 6), unpriced_models=len(v["unpriced"])) for k, v in by_kind.items()
    ]
    return UsageSummary(kinds=kinds, cost=round(sum(k.cost for k in kinds), 6), has_unpriced=any(k.unpriced_models for k in kinds))


async def _daily(match: dict, prices: dict) -> list[DailyPoint]:
    rows = await _aggregate(match, ["day", "kind", "provider_id", "model_id"])
    days: dict[str, dict] = {}
    for r in rows:
        d = days.setdefault(r["day"], {"cost": 0.0, "calls": 0})
        d["cost"] += _cost(r["kind"], r, prices.get((r["kind"], r["provider_id"], r["model_id"]))) or 0
        # one call touches several kinds; `llm` is the per-call counter (every voice turn uses it)
        if r["kind"] == "llm":
            d["calls"] += r["calls"]
    return [DailyPoint(day=k, cost=round(v["cost"], 6), calls=v["calls"]) for k, v in sorted(days.items())]


async def overview(day_from: str | None, day_to: str | None, include_test: bool) -> UsageOverview:
    match = _match(day_from, day_to, include_test)
    prices = await _prices()
    rows = await _aggregate(match, ["org_id", "kind", "provider_id", "model_id"])
    by_org: dict[str, list[dict]] = {}
    for r in rows:
        by_org.setdefault(r["org_id"], []).append(r)
    ids = [PydanticObjectId(o) for o in by_org if PydanticObjectId.is_valid(o)]
    names = {str(o.id): o.name for o in await Organization.find({"_id": {"$in": ids}}).to_list()} if ids else {}
    orgs = [OrgUsageRow(org_id=o, org_name=names.get(o, "(deleted organization)"), **_summarize(rs, prices).model_dump()) for o, rs in by_org.items()]
    orgs.sort(key=lambda o: o.cost, reverse=True)
    return UsageOverview(usd_to_inr=await get_rate(), total=_summarize(rows, prices), organizations=orgs, daily=await _daily(match, prices))


async def org_detail(org_id: str, day_from: str | None, day_to: str | None, include_test: bool) -> OrgUsageDetail:
    org = await Organization.get(PydanticObjectId(org_id)) if PydanticObjectId.is_valid(org_id) else None
    if org is None:
        raise NotFoundError("Organization not found")
    match = _match(day_from, day_to, include_test, org_id=org_id)
    prices = await _prices()
    rows = await _aggregate(match, ["kind", "provider_id", "model_id"])
    models: dict[tuple, dict] = {}
    for r in rows:
        m = models.setdefault((r["kind"], r["provider_id"], r["model_id"]), dict.fromkeys(_SUM_FIELDS, 0))
        for f in _SUM_FIELDS:
            m[f] += r[f]
    lines = []
    for (kind, provider, model), u in models.items():
        c = _cost(kind, u, prices.get((kind, provider, model)))
        lines.append(CostLine(kind=kind, provider_id=provider, model_id=model, usage=Totals(**u), cost=None if c is None else round(c, 6)))
    lines.sort(key=lambda x: (KINDS.index(x.kind), -(x.cost or 0)))
    return OrgUsageDetail(usd_to_inr=await get_rate(), org_id=org_id, org_name=org.name, total=_summarize(rows, prices), models=lines, daily=await _daily(match, prices))


# ------------------------------------------------------------------- pricing


def _price_out(p: ModelPrice) -> ModelPriceOut:
    return ModelPriceOut(**p.model_dump(include={"kind", "provider_id", "model_id", "currency", "input_per_million", "cached_input_per_million", "output_per_million", "per_minute", "per_million_chars"}))


async def list_pricing() -> PricingList:
    prices = await _prices()
    seen = await _run([{"$group": {"_id": {"kind": "$kind", "provider_id": "$provider_id", "model_id": "$model_id"}}}])
    out = {k: _price_out(p) for k, p in prices.items()}
    for s in seen:
        i = s["_id"]
        key = (i["kind"], i["provider_id"], i["model_id"])
        if key not in out:
            out[key] = ModelPriceOut(**i, priced=False)
    return PricingList(usd_to_inr=await get_rate(), prices=sorted(out.values(), key=lambda p: (KINDS.index(p.kind), p.provider_id, p.model_id)))


async def upsert_price(payload: ModelPriceIn) -> ModelPriceOut:
    existing = await ModelPrice.find_one(
        ModelPrice.kind == payload.kind, ModelPrice.provider_id == payload.provider_id, ModelPrice.model_id == payload.model_id
    )
    if existing is None:
        existing = ModelPrice(**payload.model_dump())
        await existing.insert()
    else:
        for k, v in payload.model_dump().items():
            setattr(existing, k, v)
        existing.updated_at = datetime.now(timezone.utc)
        await existing.save()
    return _price_out(existing)
