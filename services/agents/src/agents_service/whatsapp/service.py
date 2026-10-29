import asyncio
import csv
import io
import json
import re
import uuid
from datetime import datetime, timedelta, timezone

from beanie import PydanticObjectId
from common.enums import Role
from common.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError, UnprocessableEntityError
from common.log_utils import setup_logger

from agents_service.core.config import get_settings
from agents_service.core.deps import AuthContext
from agents_service.whatsapp import crypto
from agents_service.whatsapp.model import (
    FieldDef,
    WhatsAppAgent,
    WhatsAppBatch,
    WhatsAppContact,
    WhatsAppMessageEvent,
    WhatsAppSettings,
    WhatsAppTemplate,
)
from agents_service.whatsapp.schema import (
    BatchOut,
    ConnectionTestOut,
    ContactCreate,
    ContactListOut,
    ContactOut,
    ContactUpdate,
    FieldMapperUpdate,
    FieldOut,
    MessageEventOut,
    MessageStatusListOut,
    MessageStatusOut,
    RefreshRequest,
    RefreshResult,
    RowError,
    SendRequest,
    SendResult,
    SettingsOut,
    SettingsUpdate,
    StatsOut,
    TemplateCreate,
    TemplateImport,
    TemplateOut,
    TemplateUpdate,
    TwilioTemplateOut,
    UploadResult,
    WhatsAppAgentCreate,
    WhatsAppAgentOut,
    WhatsAppAgentUpdate,
    WhatsAppConfigOut,
)
from agents_service.whatsapp.twilio_client import TwilioClient, TwilioConfig, TwilioError, callback_url

logger = setup_logger(__name__)

BUILTIN_FIELDS = (FieldDef(key="full_name", type="string", required=True), FieldDef(key="phone_number", type="long", required=True))
# Keys a custom field may not use (they're columns of the contact itself).
_RESERVED_KEYS = {"full_name", "customer_name", "phone_number", "message", "id", "data"}
_FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_TRUE = {"true", "yes", "y", "1", "x", "checked", "✓"}
_FALSE = {"false", "no", "n", "0", "unchecked"}
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
# A contact stuck in `queued` this long (server restart mid-send) may be re-sent.
_STALE_QUEUE = timedelta(minutes=15)
# Statuses only move forward; a late "sent" callback must not undo "delivered".
_STATUS_RANK = {"pending": 0, "queued": 1, "sent": 2, "delivered": 3, "read": 4, "failed": 5}

# Strong refs so fire-and-forget send jobs aren't garbage-collected mid-run.
_jobs: set[asyncio.Task] = set()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _oid(value: str, what: str) -> PydanticObjectId:
    try:
        return PydanticObjectId(value)
    except Exception:
        raise NotFoundError(f"{what} not found") from None


# ---------------------------------------------------------------- mapping
def mapper_out(a: WhatsAppAgent) -> list[FieldOut]:
    return [FieldOut(**f.model_dump(), locked=True) for f in BUILTIN_FIELDS] + [
        FieldOut(**f.model_dump()) for f in a.custom_fields
    ]


def coerce_value(raw: object, ftype: str) -> object:
    """Convert one raw (CSV text or JSON) value to its MongoDB type; ValueError if it doesn't fit."""
    text = str(raw).strip()
    if ftype == "string":
        if len(text) > 1000:
            raise ValueError("longer than 1000 characters")
        return text
    if ftype == "number":
        if isinstance(raw, bool):
            raise ValueError("expected a number")
        try:
            n = float(text)
        except ValueError:
            raise ValueError(f"{text!r} is not a number") from None
        if n != n or n in (float("inf"), float("-inf")):
            raise ValueError(f"{text!r} is not a number")
        return int(n) if n.is_integer() and "." not in text and "e" not in text.lower() else n
    if ftype == "long":
        try:
            n = int(text)
        except ValueError:
            raise ValueError(f"{text!r} is not a whole number") from None
        if not -(2**63) <= n < 2**63:
            raise ValueError("out of range for a 64-bit integer")
        return n
    if ftype in ("boolean", "checkbox"):  # a checkbox is a boolean shown as a tick box in the UI
        if text.lower() in _TRUE:
            return True
        if text.lower() in _FALSE:
            return False
        raise ValueError(f"{text!r} is not a yes/no value (use true/false, yes/no, 1/0)")
    if ftype == "date":
        try:
            d = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"{text!r} is not a date (use YYYY-MM-DD)") from None
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    raise ValueError(f"unknown type {ftype}")


def coerce_data(values: dict, fields: list[FieldDef]) -> dict:
    """Validate custom-field values against the mapper; unknown keys are rejected, blanks dropped."""
    known = {f.key: f for f in fields}
    out: dict = {}
    for key, raw in values.items():
        if key not in known:
            raise ValueError(f"unknown field {key!r}")
        if raw is None or str(raw).strip() == "":
            continue
        try:
            out[key] = coerce_value(raw, known[key].type)
        except ValueError as e:
            raise ValueError(f"{key}: {e}") from None
    for f in fields:
        if f.required and f.key not in out:
            raise ValueError(f"{f.key} is required")
    return out


def agent_fields(a: WhatsAppAgent) -> list[FieldDef]:
    return list(a.custom_fields)


def allowed_placeholders(a: WhatsAppAgent) -> list[str]:
    return ["full_name", "message", *[f.key for f in a.custom_fields]]


def agent_out(a: WhatsAppAgent) -> WhatsAppAgentOut:
    return WhatsAppAgentOut(
        id=str(a.id), org_id=a.org_id, user_id=a.user_id, name=a.name, description=a.description,
        use_case=a.use_case, twilio_sender=a.twilio_sender, channel=a.channel, status=a.status, field_mapper=mapper_out(a),
        created_at=a.created_at, updated_at=a.updated_at,
    )  # fmt: skip


def template_out(t: WhatsAppTemplate) -> TemplateOut:
    return TemplateOut(
        id=str(t.id), whatsapp_agent_id=t.whatsapp_agent_id, name=t.name, language=t.language,
        category=t.category, body=t.body, variables=t.variables, var_names=t.var_names, source=t.source,
        twilio_content_sid=t.twilio_content_sid,
        approval_status=t.approval_status, rejection_reason=t.rejection_reason,
        created_at=t.created_at, updated_at=t.updated_at,
    )  # fmt: skip


def contact_out(c: WhatsAppContact) -> ContactOut:
    return ContactOut(
        id=str(c.id), whatsapp_agent_id=c.whatsapp_agent_id, batch_id=c.batch_id, customer_name=c.customer_name,
        phone_number=c.phone_number, message=c.message, data=c.data, send_status=c.send_status, opted_out=c.opted_out,
        template_id=c.template_id, twilio_message_sid=c.twilio_message_sid, error=c.error, sent_at=c.sent_at,
        created_at=c.created_at, updated_at=c.updated_at,
    )  # fmt: skip


def batch_out(b: WhatsAppBatch) -> BatchOut:
    return BatchOut(
        id=str(b.id), whatsapp_agent_id=b.whatsapp_agent_id, filename=b.filename, total_rows=b.total_rows,
        valid_rows=b.valid_rows, invalid_rows=b.invalid_rows, uploaded_by=b.uploaded_by, created_at=b.created_at,
    )  # fmt: skip


# ---------------------------------------------------------------- org settings
_SID_RE = re.compile(r"^AC[0-9a-fA-F]{32}$")
_COUNTRY_RE = re.compile(r"^\d{1,4}$")
DEFAULT_COUNTRY_CODE = "91"


async def _settings_doc(org_id: str | None) -> WhatsAppSettings | None:
    if org_id is None:
        return None
    return await WhatsAppSettings.find_one(WhatsAppSettings.org_id == org_id)


def _doc_simulated(doc: WhatsAppSettings | None) -> bool:
    return doc is None or doc.dry_run or not (doc.twilio_account_sid and doc.twilio_auth_token_enc)


async def load_config(org_id: str | None) -> TwilioConfig:
    """The org's Twilio config with the token decrypted, for actually sending.
    No saved settings = fully simulated.
    """
    doc = await _settings_doc(org_id)
    if doc is None:
        return TwilioConfig()
    token = ""
    if doc.twilio_auth_token_enc:
        try:
            token = crypto.decrypt(doc.twilio_auth_token_enc)
        except ValueError:
            logger.error("whatsapp settings for org %s: saved auth token can't be decrypted", org_id)
            raise UnprocessableEntityError(
                "The saved Twilio auth token can't be decrypted (the encryption key changed). Re-enter it in Twilio settings."
            ) from None
    return TwilioConfig(
        account_sid=doc.twilio_account_sid, auth_token=token, whatsapp_from=doc.twilio_whatsapp_from,
        sms_from=doc.twilio_sms_from, dry_run=doc.dry_run, default_country_code=doc.default_country_code,
    )  # fmt: skip


async def _country_code(org_id: str | None) -> str:
    doc = await _settings_doc(org_id)
    return doc.default_country_code if doc else DEFAULT_COUNTRY_CODE


def settings_out(doc: WhatsAppSettings | None) -> SettingsOut:
    return SettingsOut(
        twilio_account_sid=doc.twilio_account_sid if doc else "",
        has_auth_token=bool(doc and doc.twilio_auth_token_enc),
        auth_token_hint=f"••••{doc.twilio_auth_token_last4}" if doc and doc.twilio_auth_token_enc else None,
        twilio_whatsapp_from=doc.twilio_whatsapp_from if doc else "",
        twilio_sms_from=doc.twilio_sms_from if doc else "",
        dry_run=doc.dry_run if doc else True,
        default_country_code=doc.default_country_code if doc else DEFAULT_COUNTRY_CODE,
        simulated=_doc_simulated(doc),
        updated_at=doc.updated_at if doc else None,
    )  # fmt: skip


def _require_messaging(auth: AuthContext) -> None:
    """The Twilio settings are shared by both channels: an org needs at least one of them."""
    if not (auth.has_feature("whatsapp") or auth.has_feature("sms")):
        auth.require_feature("whatsapp")


async def get_settings_out(auth: AuthContext) -> SettingsOut:
    _require_messaging(auth)
    return settings_out(await _settings_doc(auth.organization_id))


async def config_out(auth: AuthContext) -> WhatsAppConfigOut:
    doc = await _settings_doc(auth.organization_id)
    return WhatsAppConfigOut(
        dry_run=_doc_simulated(doc),
        default_sender_configured=bool(doc and doc.twilio_whatsapp_from),
        default_sms_sender_configured=bool(doc and doc.twilio_sms_from),
    )


def _require_settings_admin(auth: AuthContext) -> str:
    if not (auth.is_super_admin or auth.role == Role.ADMIN):
        raise ForbiddenError("Only an Admin can change the Twilio settings")
    if auth.organization_id is None:
        raise BadRequestError("Select an organization first")
    return auth.organization_id


async def update_settings(auth: AuthContext, payload: SettingsUpdate) -> SettingsOut:
    _require_messaging(auth)
    org_id = _require_settings_admin(auth)
    doc = await _settings_doc(org_id) or WhatsAppSettings(org_id=org_id)
    ch = payload.model_dump(exclude_unset=True)

    if (sid := ch.get("twilio_account_sid")) is not None:
        sid = sid.strip()
        if sid and not _SID_RE.match(sid):
            raise UnprocessableEntityError("twilio_account_sid: expected `AC` followed by 32 hex characters")
        doc.twilio_account_sid = sid
    if (cc := ch.get("default_country_code")) is not None:
        cc = cc.strip().lstrip("+")
        if not _COUNTRY_RE.match(cc):
            raise UnprocessableEntityError("default_country_code: digits only, e.g. 91")
        doc.default_country_code = cc
    if (sender := ch.get("twilio_whatsapp_from")) is not None:
        doc.twilio_whatsapp_from = _clean_sender(sender, doc.default_country_code) or ""
    if (sms := ch.get("twilio_sms_from")) is not None:
        doc.twilio_sms_from = _clean_sender(sms, doc.default_country_code, "sms") or ""
    if (token := ch.get("auth_token")) and token.strip():
        token = token.strip()
        if len(token) < 16 or re.search(r"\s", token):
            raise UnprocessableEntityError("auth_token: doesn't look like a Twilio auth token")
        doc.twilio_auth_token_enc = crypto.encrypt(token)
        doc.twilio_auth_token_last4 = token[-4:]
    if ch.get("dry_run") is not None:
        doc.dry_run = ch["dry_run"]

    if not doc.dry_run and not (doc.twilio_account_sid and doc.twilio_auth_token_enc):
        raise UnprocessableEntityError("Real sending needs both the Account SID and the Auth Token. Save them, or keep dry-run on.")

    doc.updated_by, doc.updated_at = auth.user_id, _now()
    await doc.save()
    # Never log secret values — only which fields changed.
    logger.info("whatsapp settings updated: org=%s by=%s fields=%s", org_id, auth.user_id, sorted(ch))
    return settings_out(doc)


async def test_connection(auth: AuthContext) -> ConnectionTestOut:
    _require_messaging(auth)
    org_id = _require_settings_admin(auth)
    cfg = await load_config(org_id)
    try:
        name = await TwilioClient(cfg).verify_credentials()
    except TwilioError as e:
        return ConnectionTestOut(ok=False, detail=str(e))
    return ConnectionTestOut(ok=True, detail=f"Connected to Twilio account: {name}")


# ---------------------------------------------------------------- phone / csv
def normalize_phone(raw: str, country_code: str = DEFAULT_COUNTRY_CODE) -> str:
    """Returns E.164 or raises ValueError. A bare 10-digit number gets the
    org's default country code (India, 91, by default).
    """
    cleaned = re.sub(r"[\s\-().]", "", (raw or "").strip())
    if cleaned.startswith("whatsapp:"):
        cleaned = cleaned[len("whatsapp:") :]
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if not cleaned.startswith("+"):
        digits = cleaned.lstrip("0") if len(cleaned) == 11 and cleaned.startswith("0") else cleaned
        if not digits.isdigit():
            raise ValueError("phone number contains invalid characters")
        if len(digits) == 10:
            digits = country_code + digits
        cleaned = "+" + digits
    if not _E164_RE.match(cleaned):
        raise ValueError("not a valid phone number (expected E.164, e.g. +919876543210)")
    return cleaned


def phone_to_int(raw: str | int, country_code: str = DEFAULT_COUNTRY_CODE) -> int:
    """Normalize to E.164 and return its digits as an integer (the stored form)."""
    return int(normalize_phone(str(raw), country_code)[1:])


def parse_csv(
    text: str, country_code: str = DEFAULT_COUNTRY_CODE, fields: list[FieldDef] | None = None
) -> tuple[list[dict], list[RowError], int]:
    """Returns (valid rows, row errors, total data rows). Columns are matched by
    header: `full_name` (or legacy `customer_name`), `phone_number`, optional
    `message`, plus the agent's custom `fields`. Raises UnprocessableEntityError
    for structural problems (bad header / too big).
    """
    fields = fields or []
    max_rows = get_settings().whatsapp_max_csv_rows
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    try:
        header = next(reader)
    except StopIteration:
        raise UnprocessableEntityError("The CSV is empty") from None
    cols = [h.strip().lower() for h in header]
    name_col = next((c for c in ("full_name", "customer_name") if c in cols), None)
    required = ["full_name" if name_col is None else name_col, "phone_number", *[f.key for f in fields if f.required]]
    missing = [c for c in required if c not in cols]
    if missing:
        raise UnprocessableEntityError(
            f"CSV is missing required column(s): {', '.join(missing)}. "
            f"Expected header: {','.join(['full_name', 'phone_number', *[f.key for f in fields]])}"
        )
    idx = {c: cols.index(c) for c in cols}

    def cell(row: list[str], col: str | None) -> str:
        return row[idx[col]].strip() if col in idx and idx[col] < len(row) else ""

    valid: list[dict] = []
    errors: list[RowError] = []
    seen: set[int] = set()
    total = 0
    for line_no, row in enumerate(reader, start=2):
        if not any(c.strip() for c in row):
            continue
        total += 1
        if total > max_rows:
            raise UnprocessableEntityError(f"The CSV has more than {max_rows} rows; split it into smaller files")
        try:
            name, phone_raw, message = cell(row, name_col), cell(row, "phone_number"), cell(row, "message")
            if not name:
                raise ValueError("full_name is empty")
            if len(name) > 200:
                raise ValueError("full_name is longer than 200 characters")
            if len(message) > 1600:
                raise ValueError("message is longer than 1600 characters")
            phone = phone_to_int(phone_raw, country_code)
            if phone in seen:
                raise ValueError(f"duplicate phone number {phone} in this file")
            data = coerce_data({f.key: cell(row, f.key) for f in fields}, fields)
        except ValueError as e:
            errors.append(RowError(row=line_no, error=str(e)))
            continue
        seen.add(phone)
        valid.append({"customer_name": name, "phone_number": phone, "message": message, "data": data})
    return valid, errors, total


# ---------------------------------------------------------------- access
def _require_org(auth: AuthContext) -> str | None:
    if auth.organization_id is None and not auth.is_super_admin:
        raise ForbiddenError("No organization selected")
    return auth.organization_id


async def get_agent(agent_id: str, auth: AuthContext, *, write: bool = False) -> WhatsAppAgent:
    agent = await WhatsAppAgent.get(_oid(agent_id, "WhatsApp agent"))
    if agent is None:
        raise NotFoundError("WhatsApp agent not found")
    if not auth.is_super_admin and agent.org_id != auth.organization_id:
        # 404, not 403: don't reveal agents of other orgs.
        raise NotFoundError("WhatsApp agent not found")
    auth.require_feature(agent.channel)  # an org without SMS can't touch SMS agents, and vice versa
    if write and auth.role == Role.QA:
        raise ForbiddenError("QA role has view-only access")
    return agent


# ---------------------------------------------------------------- agents
async def create_agent(auth: AuthContext, payload: WhatsAppAgentCreate) -> WhatsAppAgent:
    if auth.role == Role.QA:
        raise ForbiddenError("QA role has view-only access")
    if auth.organization_id is None:
        raise BadRequestError("Select an organization before creating a messaging agent")
    auth.require_feature(payload.channel)
    sender = _clean_sender(payload.twilio_sender, await _country_code(auth.organization_id), payload.channel)
    agent = WhatsAppAgent(
        org_id=auth.organization_id, user_id=auth.user_id, name=payload.name, channel=payload.channel,
        description=payload.description, use_case=payload.use_case, twilio_sender=sender,
    )  # fmt: skip
    await agent.insert()
    return agent


_MESSAGING_SERVICE_RE = re.compile(r"^MG[0-9a-fA-F]{32}$")


def _clean_sender(raw: str | None, country_code: str = DEFAULT_COUNTRY_CODE, channel: str = "whatsapp") -> str | None:
    if raw is None or not raw.strip():
        return None
    if channel == "sms" and _MESSAGING_SERVICE_RE.match(raw.strip()):
        return raw.strip()  # a Twilio Messaging Service (common for India DLT)
    try:
        return normalize_phone(raw, country_code)
    except ValueError as e:
        raise UnprocessableEntityError(f"twilio_sender: {e}") from None


async def list_agents(auth: AuthContext, channel: str = "whatsapp") -> list[WhatsAppAgent]:
    auth.require_feature(channel)
    # Agents saved before SMS existed have no `channel` and are WhatsApp.
    by_channel: dict = {"channel": "sms"} if channel == "sms" else {"channel": {"$ne": "sms"}}
    if auth.organization_id is None:
        if not auth.is_super_admin:
            return []
        scope = {"user_id": auth.user_id}
    else:
        scope = {"org_id": auth.organization_id}
    return await WhatsAppAgent.find({**scope, **by_channel}).sort("-updated_at").to_list()


async def update_agent(agent_id: str, auth: AuthContext, payload: WhatsAppAgentUpdate) -> WhatsAppAgent:
    agent = await get_agent(agent_id, auth, write=True)
    changes = payload.model_dump(exclude_unset=True)
    if "twilio_sender" in changes:
        changes["twilio_sender"] = _clean_sender(changes["twilio_sender"], await _country_code(agent.org_id), agent.channel)
    if "name" in changes and changes["name"] is not None:
        changes["name"] = changes["name"].strip()
    for k, v in changes.items():
        if k in ("name", "status") and v is None:
            continue
        setattr(agent, k, v)
    agent.updated_at = _now()
    await agent.save()
    return agent


async def update_field_mapper(agent_id: str, auth: AuthContext, payload: FieldMapperUpdate) -> WhatsAppAgent:
    agent = await get_agent(agent_id, auth, write=True)
    seen: set[str] = set()
    for f in payload.fields:
        if not _FIELD_KEY_RE.match(f.key):
            raise UnprocessableEntityError(f"{f.key!r}: use lowercase letters, digits and _, starting with a letter (max 40)")
        if f.key in _RESERVED_KEYS:
            raise UnprocessableEntityError(f"{f.key!r} is a built-in field and can't be redefined")
        if f.key in seen:
            raise UnprocessableEntityError(f"Duplicate field {f.key!r}")
        seen.add(f.key)
    agent.custom_fields = [FieldDef(**f.model_dump()) for f in payload.fields]
    agent.updated_at = _now()
    await agent.save()
    return agent


async def delete_agent(agent_id: str, auth: AuthContext) -> None:
    agent = await get_agent(agent_id, auth, write=True)
    aid = str(agent.id)
    await WhatsAppMessageEvent.find(WhatsAppMessageEvent.whatsapp_agent_id == aid).delete()
    await WhatsAppContact.find(WhatsAppContact.whatsapp_agent_id == aid).delete()
    await WhatsAppBatch.find(WhatsAppBatch.whatsapp_agent_id == aid).delete()
    await WhatsAppTemplate.find(WhatsAppTemplate.whatsapp_agent_id == aid).delete()
    await agent.delete()


# ---------------------------------------------------------------- templates
def extract_variables(body: str, allowed: list[str]) -> list[str]:
    """Distinct placeholders in first-appearance order; rejects unknown ones."""
    seen: list[str] = []
    for name in _PLACEHOLDER_RE.findall(body):
        if name not in allowed and name != "customer_name":  # customer_name = legacy alias of full_name
            raise UnprocessableEntityError(
                f"Unknown placeholder {{{{{name}}}}}. Allowed: " + ", ".join(f"{{{{{p}}}}}" for p in allowed)
            )
        if name not in seen:
            seen.append(name)
    return seen


def to_twilio_body(body: str, variables: list[str]) -> str:
    return _PLACEHOLDER_RE.sub(lambda m: "{{%d}}" % (variables.index(m.group(1)) + 1), body)


def _wa_template_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")
    return slug or "template"


async def _get_template(agent: WhatsAppAgent, template_id: str) -> WhatsAppTemplate:
    t = await WhatsAppTemplate.get(_oid(template_id, "Template"))
    if t is None or t.whatsapp_agent_id != str(agent.id):
        raise NotFoundError("Template not found")
    return t


async def _assert_template_name_free(agent: WhatsAppAgent, name: str, *, except_id=None) -> None:
    existing = await WhatsAppTemplate.find_one(
        WhatsAppTemplate.whatsapp_agent_id == str(agent.id), WhatsAppTemplate.name == name
    )
    if existing is not None and existing.id != except_id:
        raise ConflictError(f"A template named '{name}' already exists for this agent")


async def create_template(agent_id: str, auth: AuthContext, payload: TemplateCreate) -> WhatsAppTemplate:
    agent = await get_agent(agent_id, auth, write=True)
    name = payload.name.strip()
    await _assert_template_name_free(agent, name)
    t = WhatsAppTemplate(
        org_id=agent.org_id, whatsapp_agent_id=str(agent.id), name=name, language=payload.language,
        category=payload.category, body=payload.body, variables=extract_variables(payload.body, allowed_placeholders(agent)),
        # SMS has no approval step: a template is usable as soon as it is saved.
        approval_status="approved" if agent.channel == "sms" else "draft",
    )  # fmt: skip
    await t.insert()
    return t


async def list_templates(agent_id: str, auth: AuthContext) -> list[WhatsAppTemplate]:
    agent = await get_agent(agent_id, auth)
    rows = await WhatsAppTemplate.find(WhatsAppTemplate.whatsapp_agent_id == str(agent.id)).sort("-created_at").to_list()
    cfg = await load_config(agent.org_id)
    return [t for t in rows if not await _drop_simulated_sid(t, cfg)]


async def update_template(agent_id: str, template_id: str, auth: AuthContext, payload: TemplateUpdate) -> WhatsAppTemplate:
    agent = await get_agent(agent_id, auth, write=True)
    t = await _get_template(agent, template_id)
    if t.source == "twilio":
        raise ConflictError("This template lives in Twilio; edit it there")
    if t.approval_status in ("pending", "approved") and agent.channel != "sms":
        raise ConflictError("Approved or pending templates can't be edited (WhatsApp templates are immutable). Create a new one.")
    changes = payload.model_dump(exclude_unset=True)
    for key in ("name", "language", "category", "body"):
        if key in changes and changes[key] is None:
            changes.pop(key)
    if "name" in changes:
        changes["name"] = changes["name"].strip()
        await _assert_template_name_free(agent, changes["name"], except_id=t.id)
    for k, v in changes.items():
        setattr(t, k, v)
    t.variables = extract_variables(t.body, allowed_placeholders(agent))
    if t.approval_status == "rejected":
        t.approval_status = "draft"
        t.rejection_reason = None
    if agent.channel == "sms":  # nothing on Twilio to recreate
        t.updated_at = _now()
        await t.save()
        return t
    # Content on Twilio is immutable: a new submit must create a fresh Content.
    old_sid, t.twilio_content_sid = t.twilio_content_sid, None
    t.updated_at = _now()
    await t.save()
    await _delete_remote_quietly(old_sid, agent.org_id)
    return t


async def delete_template(agent_id: str, template_id: str, auth: AuthContext) -> None:
    agent = await get_agent(agent_id, auth, write=True)
    t = await _get_template(agent, template_id)
    sid = t.twilio_content_sid
    await t.delete()
    if t.source == "bolotext":  # a template linked from Twilio is only unlinked, never deleted there
        await _delete_remote_quietly(sid, agent.org_id)


async def _delete_remote_quietly(content_sid: str | None, org_id: str | None) -> None:
    if not content_sid:
        return
    try:
        await TwilioClient(await load_config(org_id)).delete_template(content_sid)
    except (TwilioError, UnprocessableEntityError) as e:
        logger.warning("could not delete Twilio content %s: %s", content_sid, e)


def _twilio_failure(e: TwilioError, action: str) -> UnprocessableEntityError:
    return UnprocessableEntityError(f"Twilio rejected the request to {action}: {e}", details={"twilio_code": e.code})


_SAMPLES = {"string": "sample", "number": "100", "long": "100", "boolean": "yes", "checkbox": "yes", "date": "2026-01-31"}


def _sample_value(agent: WhatsAppAgent, name: str) -> str:
    if name in ("full_name", "customer_name"):
        return "Asha"
    if name == "message":
        return "your order is ready"
    f = next((f for f in agent.custom_fields if f.key == name), None)
    return _SAMPLES[f.type] if f else "sample"


def _var_name(t: WhatsAppTemplate, i: int) -> str:
    return t.var_names[i] if i < len(t.var_names) else str(i + 1)


def _template_value(c: WhatsAppContact, name: str) -> str:
    if name in ("full_name", "customer_name"):
        return c.customer_name
    if name == "message":
        return c.message or "-"
    v = c.data.get(name)
    if v is None:
        return "-"
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, bool):
        return "yes" if v else "no"
    return str(v)


async def _drop_simulated_sid(t: WhatsAppTemplate, cfg: TwilioConfig) -> bool:
    """A template created (or linked) in dry-run holds a fake `HXDRY…` Content SID
    that doesn't exist in Twilio. Once real sending is on, a Bolotext template goes
    back to draft so it can be submitted for real, and a linked sample is removed.
    Returns True if the template was removed.
    """
    if cfg.dry_run or not (t.twilio_content_sid or "").startswith("HXDRY"):
        return False
    if t.source == "twilio":
        await t.delete()
        return True
    t.twilio_content_sid, t.approval_status, t.rejection_reason, t.updated_at = None, "draft", None, _now()
    await t.save()
    return False


def _sendable(t: WhatsAppTemplate, agent: WhatsAppAgent | None = None) -> bool:
    """Bolotext templates need WhatsApp approval. A template linked from Twilio is
    sent unless rejected — Twilio itself refuses it if the sender isn't allowed to use it.
    """
    if agent is not None and agent.channel == "sms":
        return True  # plain text, rendered here; no WhatsApp approval involved
    if not t.twilio_content_sid:
        return False
    return t.approval_status == "approved" or (t.source == "twilio" and t.approval_status != "rejected")


async def submit_template(agent_id: str, template_id: str, auth: AuthContext) -> WhatsAppTemplate:
    agent = await get_agent(agent_id, auth, write=True)
    t = await _get_template(agent, template_id)
    if agent.channel == "sms":
        raise ConflictError("SMS templates need no approval; they can be used right away")
    cfg = await load_config(agent.org_id)
    if await _drop_simulated_sid(t, cfg):
        raise NotFoundError("Template not found")
    if t.source == "twilio":
        raise ConflictError("This template lives in Twilio; submit it for approval there, then refresh its status here")
    if t.approval_status not in ("draft", "rejected"):
        raise ConflictError(f"Template is already {t.approval_status}")
    client = TwilioClient(cfg)
    samples = {str(i + 1): _sample_value(agent, v) for i, v in enumerate(t.variables)}
    try:
        if not t.twilio_content_sid:
            t.twilio_content_sid = await client.create_template(
                name=_wa_template_name(t.name), language=t.language,
                body=to_twilio_body(t.body, t.variables), variables=samples,
            )  # fmt: skip
            await t.save()  # keep the SID even if the approval request below fails
        await client.submit_for_approval(
            content_sid=t.twilio_content_sid, name=_wa_template_name(t.name), category=t.category
        )
    except TwilioError as e:
        raise _twilio_failure(e, "submit the template") from e
    t.approval_status = "pending"
    t.rejection_reason = None
    t.updated_at = _now()
    await t.save()
    return t


_APPROVAL_MAP = {"approved": "approved", "rejected": "rejected", "pending": "pending", "received": "pending", "paused": "rejected", "disabled": "rejected"}


async def list_twilio_templates(agent_id: str, auth: AuthContext) -> list[TwilioTemplateOut]:
    """Templates that exist in the org's Twilio account, flagged with the local id if already linked."""
    agent = await get_agent(agent_id, auth)
    if agent.channel == "sms":
        return []  # Twilio Content templates are a WhatsApp concept
    try:
        remote = await TwilioClient(await load_config(agent.org_id)).list_templates()
    except TwilioError as e:
        raise _twilio_failure(e, "list templates") from e
    linked = {
        t.twilio_content_sid: str(t.id)
        for t in await WhatsAppTemplate.find(
            WhatsAppTemplate.whatsapp_agent_id == str(agent.id), WhatsAppTemplate.source == "twilio"
        ).to_list()
    }
    return [TwilioTemplateOut(**r, template_id=linked.get(r["sid"])) for r in remote]


async def import_twilio_template(agent_id: str, auth: AuthContext, payload: TemplateImport) -> WhatsAppTemplate:
    agent = await get_agent(agent_id, auth, write=True)
    if agent.channel == "sms":
        raise ConflictError("Twilio templates are for WhatsApp agents only")
    try:
        remote = await TwilioClient(await load_config(agent.org_id)).list_templates()
    except TwilioError as e:
        raise _twilio_failure(e, "list templates") from e
    r = next((x for x in remote if x["sid"] == payload.content_sid.strip()), None)
    if r is None:
        raise NotFoundError("No such template in the Twilio account")
    if await WhatsAppTemplate.find_one(
        WhatsAppTemplate.whatsapp_agent_id == str(agent.id), WhatsAppTemplate.twilio_content_sid == r["sid"]
    ):
        raise ConflictError("This Twilio template is already linked to this agent")
    allowed = allowed_placeholders(agent)
    missing = [v for v in r["variables"] if v not in payload.mapping]
    if missing:
        raise UnprocessableEntityError("Map every variable to a contact field. Missing: " + ", ".join(missing))
    bad = [f"{v} → {payload.mapping[v]}" for v in r["variables"] if payload.mapping[v] not in allowed]
    if bad:
        raise UnprocessableEntityError(f"Unknown contact field for {', '.join(bad)}. Allowed: {', '.join(allowed)}")
    await _assert_template_name_free(agent, r["name"])
    category = r["category"] if r["category"] in ("utility", "marketing", "authentication") else "utility"
    t = WhatsAppTemplate(
        org_id=agent.org_id, whatsapp_agent_id=str(agent.id), name=r["name"], language=r["language"], category=category,
        body=r["body"], variables=[payload.mapping[v] for v in r["variables"]], var_names=list(r["variables"]),
        twilio_content_sid=r["sid"], approval_status=_twilio_approval(r["approval_status"]), source="twilio",
        rejection_reason=r["rejection_reason"],
    )  # fmt: skip
    await t.insert()
    return t


def _twilio_approval(status: str) -> str:
    return _APPROVAL_MAP.get(status.lower(), "draft")  # `unsubmitted` etc. → draft


async def sync_template_status(agent_id: str, template_id: str, auth: AuthContext) -> WhatsAppTemplate:
    agent = await get_agent(agent_id, auth, write=True)
    t = await _get_template(agent, template_id)
    if agent.channel == "sms":
        raise ConflictError("SMS templates need no approval")
    cfg = await load_config(agent.org_id)
    if await _drop_simulated_sid(t, cfg):
        raise NotFoundError("Template not found")
    if not t.twilio_content_sid or (t.approval_status == "draft" and t.source != "twilio"):
        raise ConflictError("Template hasn't been submitted for approval yet")
    try:
        status, reason = await TwilioClient(cfg).approval_status(t.twilio_content_sid)
    except TwilioError as e:
        raise _twilio_failure(e, "fetch the approval status") from e
    t.approval_status = _APPROVAL_MAP.get(status.lower(), t.approval_status)  # type: ignore[assignment]
    t.rejection_reason = reason if t.approval_status == "rejected" else None
    t.updated_at = _now()
    await t.save()
    return t


# ---------------------------------------------------------------- contacts
async def upload_csv(agent_id: str, auth: AuthContext, filename: str, text: str, consent: bool) -> UploadResult:
    agent = await get_agent(agent_id, auth, write=True)
    if not consent:
        raise UnprocessableEntityError("Confirm that the recipients have opted in to WhatsApp messages before uploading")
    valid, errors, total = parse_csv(text, await _country_code(agent.org_id), agent_fields(agent))
    batch = WhatsAppBatch(
        org_id=agent.org_id, whatsapp_agent_id=str(agent.id), filename=filename or "contacts.csv",
        total_rows=total, valid_rows=len(valid), invalid_rows=len(errors), uploaded_by=auth.user_id,
    )  # fmt: skip
    await batch.insert()
    if valid:
        await WhatsAppContact.insert_many(
            [WhatsAppContact(org_id=agent.org_id, whatsapp_agent_id=str(agent.id), batch_id=str(batch.id), **row) for row in valid]
        )
    logger.info("whatsapp csv uploaded: agent=%s batch=%s valid=%d invalid=%d by=%s", agent.id, batch.id, len(valid), len(errors), auth.user_id)
    return UploadResult(batch=batch_out(batch), errors=errors)


async def list_batches(agent_id: str, auth: AuthContext) -> list[WhatsAppBatch]:
    agent = await get_agent(agent_id, auth)
    return await WhatsAppBatch.find(WhatsAppBatch.whatsapp_agent_id == str(agent.id)).sort("-created_at").to_list()


async def delete_batch(agent_id: str, batch_id: str, auth: AuthContext) -> None:
    agent = await get_agent(agent_id, auth, write=True)
    batch = await WhatsAppBatch.get(_oid(batch_id, "Batch"))
    if batch is None or batch.whatsapp_agent_id != str(agent.id):
        raise NotFoundError("Batch not found")
    ids = [str(c.id) for c in await WhatsAppContact.find(WhatsAppContact.batch_id == str(batch.id)).to_list()]
    await WhatsAppMessageEvent.find({"contact_id": {"$in": ids}}).delete()
    await WhatsAppContact.find(WhatsAppContact.batch_id == str(batch.id)).delete()
    await batch.delete()


def _phone_clauses(q: str, country_code: str) -> list[dict]:
    """Match stored integer phone numbers that start with the digits typed (with or
    without the country code) — integers can't be regex-searched, so use ranges."""
    digits = re.sub(r"[\s\-+().]", "", q)
    if len(digits) < 3 or not digits.isdigit():
        return []
    clauses = []
    for prefix in {digits.lstrip("0") or digits, country_code + digits.lstrip("0")}:
        if not prefix.isdigit():
            continue
        for extra in range(0, 16 - len(prefix)):
            lo = int(prefix) * 10**extra
            clauses.append({"phone_number": {"$gte": lo, "$lt": (int(prefix) + 1) * 10**extra}})
    return clauses


async def list_contacts(
    agent_id: str, auth: AuthContext, *, batch_id: str | None, status: str | None, q: str | None, skip: int, limit: int
) -> ContactListOut:
    agent = await get_agent(agent_id, auth)
    query: dict = {"whatsapp_agent_id": str(agent.id)}
    if batch_id:
        query["batch_id"] = batch_id
    if status:
        query["send_status"] = {"$in": [x.strip() for x in status.split(",") if x.strip()]}
    if q and q.strip():
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        query["$or"] = [{"customer_name": rx}, *_phone_clauses(q, await _country_code(agent.org_id))]
    total = await WhatsAppContact.find(query).count()
    rows = await WhatsAppContact.find(query).sort("-created_at").skip(skip).limit(limit).to_list()
    return ContactListOut(items=[contact_out(c) for c in rows], total=total)


async def contact_stats(agent_id: str, auth: AuthContext) -> StatsOut:
    agent = await get_agent(agent_id, auth)
    base = {"whatsapp_agent_id": str(agent.id)}
    counts = {s: await WhatsAppContact.find({**base, "send_status": s}).count() for s in _STATUS_RANK}
    return StatsOut(
        total=sum(counts.values()), opted_out=await WhatsAppContact.find({**base, "opted_out": True}).count(), **counts
    )


async def _get_contact(agent: WhatsAppAgent, contact_id: str) -> WhatsAppContact:
    c = await WhatsAppContact.get(_oid(contact_id, "Contact"))
    if c is None or c.whatsapp_agent_id != str(agent.id):
        raise NotFoundError("Contact not found")
    return c


def _phone_or_422(raw: str | int, country_code: str = DEFAULT_COUNTRY_CODE) -> int:
    try:
        return phone_to_int(raw, country_code)
    except ValueError as e:
        raise UnprocessableEntityError(f"phone_number: {e}") from None


def _data_or_422(agent: WhatsAppAgent, values: dict) -> dict:
    try:
        return coerce_data(values, agent_fields(agent))
    except ValueError as e:
        raise UnprocessableEntityError(f"data: {e}") from None


async def create_contact(agent_id: str, auth: AuthContext, payload: ContactCreate) -> WhatsAppContact:
    agent = await get_agent(agent_id, auth, write=True)
    phone = _phone_or_422(payload.phone_number, await _country_code(agent.org_id))
    dup = await WhatsAppContact.find_one(
        WhatsAppContact.whatsapp_agent_id == str(agent.id),
        WhatsAppContact.batch_id == None,  # noqa: E711 - beanie needs the == operator
        WhatsAppContact.phone_number == phone,
    )
    if dup is not None:
        raise ConflictError(f"{phone} was already added manually to this agent")
    c = WhatsAppContact(
        org_id=agent.org_id, whatsapp_agent_id=str(agent.id), customer_name=payload.customer_name.strip(),
        phone_number=phone, message=payload.message.strip(), data=_data_or_422(agent, payload.data),
    )  # fmt: skip
    await c.insert()
    return c


async def update_contact(agent_id: str, contact_id: str, auth: AuthContext, payload: ContactUpdate) -> WhatsAppContact:
    agent = await get_agent(agent_id, auth, write=True)
    c = await _get_contact(agent, contact_id)
    if c.send_status == "queued":
        raise ConflictError("This contact is being sent right now")
    changes = payload.model_dump(exclude_unset=True)
    content_changed = False
    if changes.get("customer_name") is not None:
        c.customer_name = changes["customer_name"].strip()
        content_changed = True
    if changes.get("message") is not None:
        c.message = changes["message"].strip()
        content_changed = True
    if changes.get("data") is not None:
        c.data = _data_or_422(agent, changes["data"])
        content_changed = True
    if changes.get("phone_number") is not None:
        phone = _phone_or_422(changes["phone_number"], await _country_code(agent.org_id))
        content_changed = content_changed or phone != c.phone_number
        c.phone_number = phone
    if changes.get("opted_out") is not None:
        c.opted_out = changes["opted_out"]
    if content_changed and c.send_status != "pending":
        # Edited after a send attempt — make it sendable again.
        c.send_status, c.twilio_message_sid, c.error, c.sent_at, c.template_id = "pending", None, None, None, None
    c.updated_at = _now()
    await c.save()
    return c


async def delete_contact(agent_id: str, contact_id: str, auth: AuthContext) -> None:
    agent = await get_agent(agent_id, auth, write=True)
    c = await _get_contact(agent, contact_id)
    await WhatsAppMessageEvent.find(WhatsAppMessageEvent.contact_id == str(c.id)).delete()
    await c.delete()


async def bulk_delete_contacts(agent_id: str, auth: AuthContext, contact_ids: list[str]) -> int:
    agent = await get_agent(agent_id, auth, write=True)
    oids = [PydanticObjectId(i) for i in contact_ids if PydanticObjectId.is_valid(i)]
    query = {"_id": {"$in": oids}, "whatsapp_agent_id": str(agent.id)}
    n = await WhatsAppContact.find(query).count()
    await WhatsAppMessageEvent.find({"contact_id": {"$in": [str(i) for i in oids]}, "whatsapp_agent_id": str(agent.id)}).delete()
    await WhatsAppContact.find(query).delete()
    return n


# ---------------------------------------------------------------- sending
async def start_send(
    agent_id: str, auth: AuthContext, payload: SendRequest, public_base: str | None = None
) -> SendResult:
    agent = await get_agent(agent_id, auth, write=True)
    if not payload.consent_confirmed:
        raise UnprocessableEntityError("Confirm that every selected recipient has opted in before sending")
    if agent.status != "active":
        raise ConflictError("This WhatsApp agent is inactive")
    if not payload.contact_ids and not payload.batch_id:
        raise BadRequestError("Provide contact_ids or batch_id")

    cfg = await load_config(agent.org_id)
    template: WhatsAppTemplate | None = None
    if payload.template_id:
        template = await _get_template(agent, payload.template_id)
        if await _drop_simulated_sid(template, cfg):
            raise NotFoundError("Template not found")
        if not _sendable(template, agent):
            raise UnprocessableEntityError(
                "Only approved templates can be sent. If this template was created in dry-run mode, submit it for approval again."
            )
    default_sender = cfg.sms_from if agent.channel == "sms" else cfg.whatsapp_from
    if not cfg.simulated and not (agent.twilio_sender or default_sender):
        kind = "SMS" if agent.channel == "sms" else "WhatsApp"
        raise UnprocessableEntityError(f"No {kind} sender configured: set one on the agent or a default in Twilio settings")

    scope: dict = {"whatsapp_agent_id": str(agent.id)}
    if payload.contact_ids:
        oids = [PydanticObjectId(i) for i in payload.contact_ids if PydanticObjectId.is_valid(i)]
        scope["_id"] = {"$in": oids}
        requested = len(payload.contact_ids)
    else:
        scope["batch_id"] = payload.batch_id
        requested = await WhatsAppContact.find(scope).count()

    job_id, now = uuid.uuid4().hex, _now()
    claimable = {
        **scope,
        "opted_out": False,
        "$or": [
            {"send_status": {"$in": ["pending", "failed"]}},
            {"send_status": "queued", "queued_at": {"$lt": now - _STALE_QUEUE}},
        ],
    }
    # Claim atomically: only contacts flipped by *this* update carry job_id, so
    # two overlapping sends can never both deliver to the same contact.
    await WhatsAppContact.find(claimable).update(
        {"$set": {
            "send_status": "queued", "send_job_id": job_id, "queued_at": now, "error": None,
            "template_id": str(template.id) if template else None,
        }}
    )  # fmt: skip
    claimed = await WhatsAppContact.find({"send_job_id": job_id}).to_list()
    ids = [str(c.id) for c in claimed]
    if ids:
        task = asyncio.create_task(
            _run_send_job(job_id, str(agent.id), template and str(template.id), ids, callback_url(public_base))
        )
        _jobs.add(task)
        task.add_done_callback(_jobs.discard)
    logger.info("whatsapp send: agent=%s job=%s requested=%d queued=%d by=%s", agent.id, job_id, requested, len(ids), auth.user_id)
    return SendResult(job_id=job_id, requested=requested, queued=len(ids), skipped=max(requested - len(ids), 0), dry_run=cfg.simulated)


# What the operator should do about the Twilio errors we see most.
_TWILIO_HINTS = {
    "63007": "The From number is not a WhatsApp sender in this Twilio account. Use your approved WhatsApp sender, or the sandbox number +14155238886 (activated in the same account), in the agent's sender or Twilio settings.",
    "63015": "The recipient hasn't joined the WhatsApp sandbox yet; they must send the join code to the sandbox number first.",
    "63016": "Outside the 24-hour window a template is required; send with an approved template.",
    "21606": "The From number can't send SMS. Use an SMS-capable Twilio number (or a Messaging Service SID) as the sender.",
    "21608": "Trial accounts can only text verified numbers. Verify the recipient in Twilio, or upgrade the account.",
    "21211": "The recipient number isn't valid.",
    "21408": "SMS to this country isn't enabled. Turn it on under Twilio → Messaging → Geo permissions.",
    "21610": "The recipient replied STOP and has unsubscribed from this sender.",
    "21614": "The recipient number can't receive SMS (not a mobile number).",
    "30007": "The carrier filtered the message. For India, the sender and template must be registered on DLT.",
    "30003": "The handset is unreachable (off, out of coverage).",
    "30008": "Delivery failed for an unknown reason; check the Twilio error log.",
}  # fmt: skip


def _hint(code: object) -> str:
    h = _TWILIO_HINTS.get(str(code))
    return f". {h}" if h else ""


def _render(body: str, c: WhatsAppContact) -> str:
    """Fill a plain-text (SMS) template's `{{placeholders}}` from the contact."""
    return _PLACEHOLDER_RE.sub(lambda m: _template_value(c, m.group(1)), body)


async def _send_one(
    client: TwilioClient, agent: WhatsAppAgent, template: WhatsAppTemplate | None, c: WhatsAppContact, callback: str | None
) -> None:
    sms = agent.channel == "sms"
    sender = agent.twilio_sender or (client.config.sms_from if sms else client.config.whatsapp_from)
    try:
        if sms:
            text = _render(template.body, c) if template else c.message
            if not text.strip():
                raise TwilioError("This contact has no message text; pick a template or add a message")
            sid = await client.send_message(
                to=f"+{c.phone_number}", sender=sender, body=text, status_callback=callback, channel="sms"
            )
        elif template:
            # A template without placeholders must not carry ContentVariables (Twilio rejects "{}").
            variables = (
                json.dumps({_var_name(template, i): _template_value(c, v) for i, v in enumerate(template.variables)})
                if template.variables
                else None
            )
            sid = await client.send_message(
                to=f"+{c.phone_number}", sender=sender, content_sid=template.twilio_content_sid,
                content_variables=variables, status_callback=callback,
            )  # fmt: skip
        else:
            if not c.message:
                raise TwilioError("This contact has no message text; pick a template or add a message")
            sid = await client.send_message(
                to=f"+{c.phone_number}", sender=sender, body=c.message, status_callback=callback
            )
        c.send_status, c.twilio_message_sid, c.error, c.sent_at = "sent", sid, None, _now()
        await _record_event(c, "simulated" if client.dry_run else "queued", "send", {"MessageSid": sid})
    except TwilioError as e:
        c.send_status, c.error = "failed", f"{e} (code {e.code}){_hint(e.code)}" if e.code else str(e)
        await _record_event(c, "failed", "send", {"ErrorCode": str(e.code or ""), "ErrorMessage": f"{e}{_hint(e.code)}"})
    except Exception as e:  # noqa: BLE001 - one bad row must never kill the job
        logger.exception("unexpected error sending to contact %s", c.id)
        c.send_status, c.error = "failed", f"Unexpected error: {e}"
        await _record_event(c, "failed", "send", {"ErrorMessage": str(e)})
    c.updated_at = _now()
    await c.save()


async def _run_send_job(
    job_id: str, agent_id: str, template_id: str | None, contact_ids: list[str], callback: str | None
) -> None:
    settings = get_settings()
    try:
        agent = await WhatsAppAgent.get(PydanticObjectId(agent_id))
        template = await WhatsAppTemplate.get(PydanticObjectId(template_id)) if template_id else None
        client = TwilioClient(await load_config(agent.org_id))
        sem = asyncio.Semaphore(max(settings.whatsapp_send_concurrency, 1))
        delay = settings.whatsapp_send_delay_ms / 1000

        async def work(cid: str) -> None:
            async with sem:
                c = await WhatsAppContact.get(PydanticObjectId(cid))
                # Deleted or re-claimed by a newer job while we waited.
                if c is None or c.send_job_id != job_id or c.send_status != "queued":
                    return
                await _send_one(client, agent, template, c, callback)  # type: ignore[arg-type]
                await asyncio.sleep(delay)

        await asyncio.gather(*(work(i) for i in contact_ids))
    except Exception:
        logger.exception("whatsapp send job %s crashed", job_id)
        await WhatsAppContact.find({"send_job_id": job_id, "send_status": "queued"}).update(
            {"$set": {"send_status": "failed", "error": "Send job crashed; try again"}}
        )


# ---------------------------------------------------------------- webhook
_TWILIO_STATUS_MAP = {
    "queued": "queued", "accepted": "queued", "scheduled": "queued", "sending": "queued",
    "sent": "sent", "delivered": "delivered", "read": "read", "failed": "failed", "undelivered": "failed",
    "canceled": "failed",
}  # fmt: skip


async def find_contact_by_sid(params: dict[str, str]) -> WhatsAppContact | None:
    sid = params.get("MessageSid") or params.get("SmsSid")
    if not sid:
        return None
    return await WhatsAppContact.find_one(WhatsAppContact.twilio_message_sid == sid)


# Raw Twilio statuses only move forward on the contact; every one is still logged as an event.
_RAW_RANK = {
    "simulated": 0, "accepted": 1, "scheduled": 1, "queued": 1, "sending": 2, "sent": 3, "delivered": 4, "read": 5,
    "undelivered": 6, "failed": 6, "canceled": 6,
}  # fmt: skip


async def _record_event(c: WhatsAppContact, status: str, source: str, payload: dict[str, str]) -> None:
    """Log one status event and fold it into the contact's latest raw status."""
    code = payload.get("ErrorCode") or None
    message = payload.get("ErrorMessage") or None
    await WhatsAppMessageEvent(
        org_id=c.org_id, whatsapp_agent_id=c.whatsapp_agent_id, contact_id=str(c.id),
        message_sid=payload.get("MessageSid") or c.twilio_message_sid, status=status, error_code=code,
        error_message=message, source=source, payload={"MessageStatus": status, **payload},  # type: ignore[arg-type]
    ).insert()  # fmt: skip
    if _RAW_RANK.get(status, 0) >= _RAW_RANK.get(c.twilio_status or "", -1):
        c.twilio_status, c.twilio_status_at = status, _now()
        c.twilio_error_code, c.twilio_error_message = code, message


async def apply_status_callback(c: WhatsAppContact, params: dict[str, str], source: str = "webhook") -> bool:
    raw = (params.get("MessageStatus") or params.get("SmsStatus") or "").lower()
    new = _TWILIO_STATUS_MAP.get(raw)
    if not new:
        return False
    await _record_event(c, raw, source, params)
    if new == "queued" or _STATUS_RANK[new] < _STATUS_RANK.get(c.send_status, 0) and c.send_status != "failed":
        c.updated_at = _now()
        await c.save()  # keeps the raw status; the simplified one never moves back
        return True
    c.send_status = new  # type: ignore[assignment]
    if new == "failed":
        code = params.get("ErrorCode")
        c.error = f"Delivery failed (code {code}){_hint(code)}" if code else "Delivery failed"
    else:
        c.error = None
    c.updated_at = _now()
    await c.save()
    return True


# ---------------------------------------------------------------- message status
_FINAL = ("read", "failed", "undelivered", "canceled")
_REFRESH_LIMIT = 100


async def refresh_message_status(agent_id: str, auth: AuthContext, payload: RefreshRequest) -> RefreshResult:
    """Ask Twilio for the current status of messages that are still in flight (or the
    given contacts) and store anything new — for when callbacks can't reach us.
    """
    agent = await get_agent(agent_id, auth)
    query: dict = {"whatsapp_agent_id": str(agent.id), "twilio_message_sid": {"$ne": None}}
    if payload.contact_ids is not None:
        query["_id"] = {"$in": [PydanticObjectId(i) for i in payload.contact_ids if PydanticObjectId.is_valid(i)]}
    else:
        query["twilio_status"] = {"$nin": list(_FINAL)}
    contacts = await WhatsAppContact.find(query).sort("-twilio_status_at").limit(_REFRESH_LIMIT).to_list()
    client = TwilioClient(await load_config(agent.org_id))
    sem = asyncio.Semaphore(max(get_settings().whatsapp_send_concurrency, 1))
    result = {"checked": 0, "updated": 0, "errors": 0, "simulated": 0}

    async def one(c: WhatsAppContact) -> None:
        async with sem:
            try:
                fetched = await client.fetch_message(c.twilio_message_sid or "")
            except TwilioError as e:
                logger.warning("could not fetch Twilio message %s: %s", c.twilio_message_sid, e)
                result["errors"] += 1
                return
        if fetched is None:
            result["simulated"] += 1
            return
        result["checked"] += 1
        status = fetched.get("MessageStatus", "").lower()
        # Only log a new event when something actually changed.
        if status != (c.twilio_status or "") or fetched.get("ErrorCode") != c.twilio_error_code:
            if await apply_status_callback(c, fetched, "refresh"):
                result["updated"] += 1

    await asyncio.gather(*(one(c) for c in contacts))
    return RefreshResult(**result)


async def list_message_status(
    agent_id: str, auth: AuthContext, *, status: str | None, q: str | None, skip: int, limit: int
) -> MessageStatusListOut:
    agent = await get_agent(agent_id, auth)
    # Only contacts a send was attempted for.
    query: dict = {"whatsapp_agent_id": str(agent.id), "twilio_status": {"$ne": None}}
    if status:
        query["twilio_status"] = status.lower()
    if q and q.strip():
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        query["$or"] = [{"customer_name": rx}, {"twilio_message_sid": rx}, *_phone_clauses(q, await _country_code(agent.org_id))]
    total = await WhatsAppContact.find(query).count()
    rows = await WhatsAppContact.find(query).sort("-twilio_status_at").skip(skip).limit(limit).to_list()
    items = []
    for c in rows:
        n = await WhatsAppMessageEvent.find({"contact_id": str(c.id)}).count()
        items.append(
            MessageStatusOut(
                contact_id=str(c.id), customer_name=c.customer_name, phone_number=c.phone_number,
                message_sid=c.twilio_message_sid, status=c.twilio_status, send_status=c.send_status,
                error_code=c.twilio_error_code, error_message=c.twilio_error_message, sent_at=c.sent_at,
                status_at=c.twilio_status_at, events=n,
            )
        )  # fmt: skip
    return MessageStatusListOut(items=items, total=total)


async def list_message_events(agent_id: str, contact_id: str, auth: AuthContext) -> list[MessageEventOut]:
    agent = await get_agent(agent_id, auth)
    c = await _get_contact(agent, contact_id)
    rows = await WhatsAppMessageEvent.find({"contact_id": str(c.id)}).sort("+received_at").to_list()
    return [
        MessageEventOut(
            id=str(e.id), message_sid=e.message_sid, status=e.status, error_code=e.error_code,
            error_message=e.error_message, source=e.source, payload=e.payload, received_at=e.received_at,
        )
        for e in rows
    ]  # fmt: skip
