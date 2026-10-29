from urllib.parse import parse_qsl

from common.errors import ForbiddenError
from common.log_utils import setup_logger
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends, Query, Request

from agents_service.core.deps import AuthContext, get_current_auth
from agents_service.whatsapp import service
from agents_service.whatsapp.schema import (
    BatchOut,
    BulkDelete,
    ContactCreate,
    ContactListOut,
    ContactOut,
    ConnectionTestOut,
    ContactUpdate,
    CsvUpload,
    FieldMapperUpdate,
    MessageEventOut,
    MessageStatusListOut,
    RefreshRequest,
    RefreshResult,
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
from agents_service.whatsapp.twilio_client import STATUS_CALLBACK_PATH, verify_signature

logger = setup_logger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


def _public_base(request: Request) -> str | None:
    """The public URL the API gateway was reached on (set by the gateway)."""
    return request.headers.get("X-Public-Base-Url") or None


@router.get("/config", response_model=SuccessResponse[WhatsAppConfigOut], summary="WhatsApp messaging configuration")
async def get_config(auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Whether the caller's organization sends for real or simulates (dry-run).
    Never returns credentials.

    **Auth:** bearer JWT required.
    """
    return success_response(data=await service.config_out(auth))


@router.get("/settings", response_model=SuccessResponse[SettingsOut], summary="Get the organization's Twilio settings")
async def get_settings_route(auth: AuthContext = Depends(get_current_auth)) -> dict:
    """The caller's organization's Twilio settings. The auth token is never
    returned — only whether one is saved and its last 4 characters.

    **Auth:** bearer JWT required (any role in the organization).
    """
    return success_response(data=await service.get_settings_out(auth))


@router.put("/settings", response_model=SuccessResponse[SettingsOut], summary="Update the organization's Twilio settings")
async def update_settings(payload: SettingsUpdate, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Partial update of the organization's Twilio settings (Account SID, auth
    token, default sender, dry-run, default country code, webhook base URL).
    The auth token is stored encrypted and can be replaced but never read back.

    **Auth:** bearer JWT; Admin (or Super Admin) of the selected organization.

    **Errors:**
    - `FORBIDDEN` — caller isn't an Admin.
    - `BAD_REQUEST` — no organization selected.
    - `UNPROCESSABLE_ENTITY` — a malformed value, or dry-run turned off without credentials.
    """
    return success_response(message="Twilio settings saved", data=await service.update_settings(auth, payload))


@router.post("/settings/test", response_model=SuccessResponse[ConnectionTestOut], summary="Test the saved Twilio credentials")
async def test_settings(auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Checks the saved Account SID/auth token against Twilio. Always reports
    success in dry-run. A failed check is returned as `ok: false`, not an error.

    **Auth:** bearer JWT; Admin (or Super Admin) of the selected organization.

    **Errors:**
    - `FORBIDDEN` — caller isn't an Admin.
    - `BAD_REQUEST` — no organization selected.
    """
    return success_response(data=await service.test_connection(auth))


# ---------------------------------------------------------------- agents
@router.post("/agents", response_model=SuccessResponse[WhatsAppAgentOut], summary="Create a messaging agent (WhatsApp or SMS)")
async def create_agent(payload: WhatsAppAgentCreate, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Creates a messaging agent for one outbound use case in the caller's organization.

    **Auth:** bearer JWT; an organization must be selected.

    **Errors:**
    - `BAD_REQUEST` — no organization selected.
    - `UNPROCESSABLE_ENTITY` — invalid `twilio_sender`.
    - `FORBIDDEN` — QA role is view-only.
    """
    agent = await service.create_agent(auth, payload)
    return success_response(code=201, message="WhatsApp agent created", data=service.agent_out(agent))


@router.get("/agents", response_model=SuccessResponse[list[WhatsAppAgentOut]], summary="List WhatsApp agents")
async def list_agents(
    channel: str = Query("whatsapp", pattern="^(whatsapp|sms)$", description="Which kind of messaging agents to list."),
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    """Every messaging agent of the given channel in the caller's organization, most recently updated first.

    **Auth:** bearer JWT required.
    """
    return success_response(data=[service.agent_out(a) for a in await service.list_agents(auth, channel)])


@router.get("/agents/{agent_id}", response_model=SuccessResponse[WhatsAppAgentOut], summary="Get a WhatsApp agent")
async def get_agent(agent_id: str, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """**Auth:** bearer JWT required.

    **Errors:**
    - `NOT_FOUND` — no such WhatsApp agent/resource in the caller's organization.
    """
    return success_response(data=service.agent_out(await service.get_agent(agent_id, auth)))


@router.patch("/agents/{agent_id}", response_model=SuccessResponse[WhatsAppAgentOut], summary="Update a WhatsApp agent")
async def update_agent(agent_id: str, payload: WhatsAppAgentUpdate, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Partial update (name, description, use case, sender, status).

    **Auth:** bearer JWT required.

    **Errors:**
    - `NOT_FOUND` — no such WhatsApp agent/resource in the caller's organization.
    - `FORBIDDEN` — QA role is view-only.
    """
    return success_response(message="WhatsApp agent updated", data=service.agent_out(await service.update_agent(agent_id, auth, payload)))


@router.put("/agents/{agent_id}/field-mapper", response_model=SuccessResponse[WhatsAppAgentOut], summary="Set the upload field mapper")
async def update_field_mapper(agent_id: str, payload: FieldMapperUpdate, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Defines the custom columns (key + data type) of this agent's uploaded
    data, on top of the built-in `full_name` and `phone_number`. CSV cells are
    validated and stored with these types in MongoDB. Existing contacts are not
    rewritten.

    **Auth:** bearer JWT required.

    **Errors:**
    - `NOT_FOUND` — no such WhatsApp agent in the caller's organization.
    - `FORBIDDEN` — QA role is view-only.
    - `UNPROCESSABLE_ENTITY` — invalid, duplicate or reserved key.
    """
    return success_response(data=service.agent_out(await service.update_field_mapper(agent_id, auth, payload)))


@router.delete("/agents/{agent_id}", response_model=SuccessResponse[None], summary="Delete a WhatsApp agent")
async def delete_agent(agent_id: str, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Deletes the agent and cascades to its templates, uploads and contacts.

    **Auth:** bearer JWT required.

    **Errors:**
    - `NOT_FOUND` — no such WhatsApp agent/resource in the caller's organization.
    - `FORBIDDEN` — QA role is view-only.
    """
    await service.delete_agent(agent_id, auth)
    return success_response(message="WhatsApp agent deleted")


# ---------------------------------------------------------------- templates
@router.post("/agents/{agent_id}/templates", response_model=SuccessResponse[TemplateOut], summary="Create a template (draft)")
async def create_template(agent_id: str, payload: TemplateCreate, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Creates a draft template. Use `{{customer_name}}` / `{{message}}` placeholders.
    Submit it for WhatsApp approval with `POST .../templates/{id}/submit`.

    **Auth:** bearer JWT required.

    **Errors:**
    - `CONFLICT` — a template with this name already exists.
    - `UNPROCESSABLE_ENTITY` — unknown placeholder.
    - `NOT_FOUND` — no such WhatsApp agent/resource in the caller's organization.
    - `FORBIDDEN` — QA role is view-only.
    """
    return success_response(code=201, message="Template created", data=service.template_out(await service.create_template(agent_id, auth, payload)))


@router.get("/agents/{agent_id}/templates", response_model=SuccessResponse[list[TemplateOut]], summary="List templates")
async def list_templates(agent_id: str, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """**Auth:** bearer JWT required.

    **Errors:**
    - `NOT_FOUND` — no such WhatsApp agent/resource in the caller's organization.
    """
    return success_response(data=[service.template_out(t) for t in await service.list_templates(agent_id, auth)])


@router.get("/agents/{agent_id}/twilio-templates", response_model=SuccessResponse[list[TwilioTemplateOut]], summary="List templates in the Twilio account")
async def list_twilio_templates(agent_id: str, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Content templates created on the Twilio platform (live from Twilio), with
    their WhatsApp approval status. `template_id` is set once linked to this agent.

    **Auth:** bearer JWT required.

    **Errors:**
    - `NOT_FOUND` — no such WhatsApp agent in the caller's organization.
    - `UNPROCESSABLE_ENTITY` — Twilio rejected the request (bad credentials, etc.).
    """
    return success_response(data=await service.list_twilio_templates(agent_id, auth))


@router.post("/agents/{agent_id}/templates/import", response_model=SuccessResponse[TemplateOut], summary="Link a Twilio-created template")
async def import_twilio_template(agent_id: str, payload: TemplateImport, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Links a template that exists in Twilio to this agent so it can be used for
    sends. `mapping` says which contact field fills each Twilio variable. The
    template stays managed in Twilio: it can't be edited or submitted here, and
    removing it here doesn't delete it in Twilio.

    **Auth:** bearer JWT required.

    **Errors:**
    - `NOT_FOUND` — no such agent, or no such template in Twilio.
    - `FORBIDDEN` — QA role is view-only.
    - `CONFLICT` — already linked, or the name is taken.
    - `UNPROCESSABLE_ENTITY` — a variable is unmapped or mapped to an unknown field.
    """
    return success_response(code=201, data=service.template_out(await service.import_twilio_template(agent_id, auth, payload)))


@router.patch("/agents/{agent_id}/templates/{template_id}", response_model=SuccessResponse[TemplateOut], summary="Edit a draft/rejected template")
async def update_template(agent_id: str, template_id: str, payload: TemplateUpdate, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Only `draft` and `rejected` templates are editable; a rejected one returns to `draft`.

    **Auth:** bearer JWT required.

    **Errors:**
    - `CONFLICT` — template is pending/approved, or the name is taken.
    - `NOT_FOUND` — no such WhatsApp agent/resource in the caller's organization.
    - `FORBIDDEN` — QA role is view-only.
    """
    return success_response(message="Template updated", data=service.template_out(await service.update_template(agent_id, template_id, auth, payload)))


@router.delete("/agents/{agent_id}/templates/{template_id}", response_model=SuccessResponse[None], summary="Delete a template")
async def delete_template(agent_id: str, template_id: str, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Deletes the template (and its Twilio Content, best-effort).

    **Auth:** bearer JWT required.

    **Errors:**
    - `NOT_FOUND` — no such WhatsApp agent/resource in the caller's organization.
    - `FORBIDDEN` — QA role is view-only.
    """
    await service.delete_template(agent_id, template_id, auth)
    return success_response(message="Template deleted")


@router.post("/agents/{agent_id}/templates/{template_id}/submit", response_model=SuccessResponse[TemplateOut], summary="Submit a template for WhatsApp approval")
async def submit_template(agent_id: str, template_id: str, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Creates the Twilio Content template and requests WhatsApp approval; status becomes `pending`.

    **Auth:** bearer JWT required.

    **Errors:**
    - `CONFLICT` — already pending/approved.
    - `UNPROCESSABLE_ENTITY` — Twilio rejected the request.
    - `NOT_FOUND` — no such WhatsApp agent/resource in the caller's organization.
    - `FORBIDDEN` — QA role is view-only.
    """
    return success_response(message="Template submitted for approval", data=service.template_out(await service.submit_template(agent_id, template_id, auth)))


@router.post("/agents/{agent_id}/templates/{template_id}/sync-status", response_model=SuccessResponse[TemplateOut], summary="Refresh a template's approval status from Twilio")
async def sync_template_status(agent_id: str, template_id: str, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """**Auth:** bearer JWT required.

    **Errors:**
    - `CONFLICT` — not submitted yet.
    - `UNPROCESSABLE_ENTITY` — Twilio request failed.
    - `NOT_FOUND` — no such WhatsApp agent/resource in the caller's organization.
    - `FORBIDDEN` — QA role is view-only.
    """
    return success_response(message="Template status refreshed", data=service.template_out(await service.sync_template_status(agent_id, template_id, auth)))


# ---------------------------------------------------------------- contacts / uploads
@router.post("/agents/{agent_id}/contacts/upload", response_model=SuccessResponse[UploadResult], summary="Upload contacts from CSV")
async def upload_contacts(agent_id: str, payload: CsvUpload, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Imports a CSV (JSON body with the raw text) with the header
    `customer_name,phone_number,message`. Valid rows are stored for this agent;
    invalid/duplicate rows are skipped and reported with their line number.
    Phone numbers are normalised to E.164 (bare 10-digit numbers get the default country code).

    **Auth:** bearer JWT required.

    **Errors:**
    - `UNPROCESSABLE_ENTITY` — consent not confirmed, bad header, empty file, or too many rows.
    - `NOT_FOUND` — no such WhatsApp agent/resource in the caller's organization.
    - `FORBIDDEN` — QA role is view-only.
    """
    res = await service.upload_csv(agent_id, auth, payload.filename, payload.csv, payload.consent_confirmed)
    return success_response(code=201, message=f"Imported {res.batch.valid_rows} contacts", data=res)


@router.get("/agents/{agent_id}/batches", response_model=SuccessResponse[list[BatchOut]], summary="List CSV uploads")
async def list_batches(agent_id: str, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """**Auth:** bearer JWT required.

    **Errors:**
    - `NOT_FOUND` — no such WhatsApp agent/resource in the caller's organization.
    """
    return success_response(data=[service.batch_out(b) for b in await service.list_batches(agent_id, auth)])


@router.delete("/agents/{agent_id}/batches/{batch_id}", response_model=SuccessResponse[None], summary="Delete an upload and its contacts")
async def delete_batch(agent_id: str, batch_id: str, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """**Auth:** bearer JWT required.

    **Errors:**
    - `NOT_FOUND` — no such WhatsApp agent/resource in the caller's organization.
    - `FORBIDDEN` — QA role is view-only.
    """
    await service.delete_batch(agent_id, batch_id, auth)
    return success_response(message="Upload deleted")


@router.get("/agents/{agent_id}/contacts", response_model=SuccessResponse[ContactListOut], summary="List contacts")
async def list_contacts(
    agent_id: str,
    batch_id: str | None = Query(None),
    status: str | None = Query(None, description="pending, queued, sent, delivered, read or failed; comma-separate to match several."),
    q: str | None = Query(None, description="Search name or phone number."),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    """Paginated, filterable contacts with the total match count.

    **Auth:** bearer JWT required.

    **Errors:**
    - `NOT_FOUND` — no such WhatsApp agent/resource in the caller's organization.
    """
    return success_response(data=await service.list_contacts(agent_id, auth, batch_id=batch_id, status=status, q=q, skip=skip, limit=limit))


@router.get("/agents/{agent_id}/stats", response_model=SuccessResponse[StatsOut], summary="Contact delivery stats")
async def contact_stats(agent_id: str, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Counts of contacts per send status.

    **Auth:** bearer JWT required.

    **Errors:**
    - `NOT_FOUND` — no such WhatsApp agent/resource in the caller's organization.
    """
    return success_response(data=await service.contact_stats(agent_id, auth))


@router.get("/agents/{agent_id}/messages", response_model=SuccessResponse[MessageStatusListOut], summary="Actual delivery status of sent messages")
async def list_message_status(
    agent_id: str,
    status: str | None = Query(None, description="Raw Twilio status, e.g. queued, sent, delivered, read, undelivered, failed."),
    q: str | None = Query(None, description="Search name, phone number or message SID."),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    """Every message a send was attempted for, with the latest status Twilio
    actually reported (not the simplified contact status).

    **Auth:** bearer JWT required.

    **Errors:**
    - `NOT_FOUND` — no such WhatsApp agent in the caller's organization.
    """
    return success_response(data=await service.list_message_status(agent_id, auth, status=status, q=q, skip=skip, limit=limit))


@router.post("/agents/{agent_id}/messages/refresh", response_model=SuccessResponse[RefreshResult], summary="Fetch current message statuses from Twilio")
async def refresh_message_status(agent_id: str, payload: RefreshRequest | None = None, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Asks Twilio for the current status of messages still in flight (or of the
    given `contact_ids`) and stores any change, with the full Twilio response, as a
    new event. Use it when status callbacks can't reach the platform. At most 100
    messages per call; simulated (dry-run) messages are skipped.

    **Auth:** bearer JWT required.

    **Errors:**
    - `NOT_FOUND` — no such WhatsApp agent in the caller's organization.
    """
    res = await service.refresh_message_status(agent_id, auth, payload or RefreshRequest())
    return success_response(message=f"Checked {res.checked} message(s), {res.updated} updated", data=res)


@router.get("/agents/{agent_id}/messages/{contact_id}/events", response_model=SuccessResponse[list[MessageEventOut]], summary="Status history of one message")
async def list_message_events(agent_id: str, contact_id: str, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Every status event stored for the message, oldest first, with the full
    Twilio callback payload.

    **Auth:** bearer JWT required.

    **Errors:**
    - `NOT_FOUND` — no such WhatsApp agent/contact in the caller's organization.
    """
    return success_response(data=await service.list_message_events(agent_id, contact_id, auth))


@router.post("/agents/{agent_id}/contacts", response_model=SuccessResponse[ContactOut], summary="Add one contact")
async def create_contact(agent_id: str, payload: ContactCreate, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """**Auth:** bearer JWT required.

    **Errors:**
    - `CONFLICT` — number already added manually.
    - `UNPROCESSABLE_ENTITY` — invalid phone number.
    - `NOT_FOUND` — no such WhatsApp agent/resource in the caller's organization.
    - `FORBIDDEN` — QA role is view-only.
    """
    return success_response(code=201, message="Contact added", data=service.contact_out(await service.create_contact(agent_id, auth, payload)))


@router.patch("/agents/{agent_id}/contacts/{contact_id}", response_model=SuccessResponse[ContactOut], summary="Edit a contact")
async def update_contact(agent_id: str, contact_id: str, payload: ContactUpdate, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Editing a contact's name/phone/message after a send attempt makes it
    `pending` again. `opted_out=true` excludes it from every send.

    **Auth:** bearer JWT required.

    **Errors:**
    - `CONFLICT` — the contact is being sent right now.
    - `UNPROCESSABLE_ENTITY` — invalid phone number.
    - `NOT_FOUND` — no such WhatsApp agent/resource in the caller's organization.
    - `FORBIDDEN` — QA role is view-only.
    """
    return success_response(message="Contact updated", data=service.contact_out(await service.update_contact(agent_id, contact_id, auth, payload)))


@router.delete("/agents/{agent_id}/contacts/{contact_id}", response_model=SuccessResponse[None], summary="Delete a contact")
async def delete_contact(agent_id: str, contact_id: str, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """**Auth:** bearer JWT required.

    **Errors:**
    - `NOT_FOUND` — no such WhatsApp agent/resource in the caller's organization.
    - `FORBIDDEN` — QA role is view-only.
    """
    await service.delete_contact(agent_id, contact_id, auth)
    return success_response(message="Contact deleted")


@router.post("/agents/{agent_id}/contacts/bulk-delete", response_model=SuccessResponse[int], summary="Delete several contacts")
async def bulk_delete_contacts(agent_id: str, payload: BulkDelete, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Returns how many contacts were deleted.

    **Auth:** bearer JWT required.

    **Errors:**
    - `NOT_FOUND` — no such WhatsApp agent/resource in the caller's organization.
    - `FORBIDDEN` — QA role is view-only.
    """
    n = await service.bulk_delete_contacts(agent_id, auth, payload.contact_ids)
    return success_response(message=f"Deleted {n} contacts", data=n)


# ---------------------------------------------------------------- send
@router.post("/agents/{agent_id}/send", response_model=SuccessResponse[SendResult], summary="Send WhatsApp messages")
async def send_messages(
    agent_id: str, payload: SendRequest, request: Request, auth: AuthContext = Depends(get_current_auth)
) -> dict:
    """Queues messages to the selected contacts (`contact_ids`) or a whole
    upload (`batch_id`) and returns immediately; delivery runs in the
    background with rate limiting, and each contact's `send_status` is updated
    as it goes (poll `GET .../contacts`, or Twilio's status callback refines it
    to delivered/read/failed). With `template_id` (must be approved) the
    template is sent; without it each contact's `message` is sent as free text,
    which WhatsApp only delivers inside the 24-hour customer-service window.
    The delivery-status callback URL is derived from the gateway's public URL
    (`X-Public-Base-Url`), so nothing needs configuring. Contacts already queued/sent/delivered or opted out are skipped, so a
    repeat click never double-sends. In dry-run mode nothing reaches Twilio.

    **Auth:** bearer JWT required.

    **Errors:**
    - `UNPROCESSABLE_ENTITY` — consent not confirmed, template not approved, or no sender configured.
    - `CONFLICT` — the agent is inactive.
    - `BAD_REQUEST` — neither `contact_ids` nor `batch_id` given.
    - `NOT_FOUND` — no such WhatsApp agent/resource in the caller's organization.
    - `FORBIDDEN` — QA role is view-only.
    """
    res = await service.start_send(agent_id, auth, payload, _public_base(request))
    return success_response(code=202 if res.queued else 200, message=f"Queued {res.queued} messages", data=res)


# ---------------------------------------------------------------- webhook
status_router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


@status_router.post("/twilio/status-callback", response_model=SuccessResponse[None], summary="Twilio delivery-status webhook")
async def twilio_status_callback(request: Request) -> dict:
    """Public endpoint called by Twilio (form-encoded) as a message moves to
    sent / delivered / read / failed. Authenticated by the `X-Twilio-Signature`
    HMAC, verified with the auth token of the organization that owns the
    message — not a bearer token. Unknown message SIDs are acknowledged and
    ignored.

    **Errors:**
    - `FORBIDDEN` — signature missing/invalid, or the organization's credentials are incomplete.
    """
    params = dict(parse_qsl((await request.body()).decode(), keep_blank_values=True))
    contact = await service.find_contact_by_sid(params)
    if contact is None:
        return success_response()
    cfg = await service.load_config(contact.org_id)
    if not cfg.simulated:
        base = _public_base(request)
        url = base + STATUS_CALLBACK_PATH if base else str(request.url)
        if not verify_signature(cfg.auth_token, url, params, request.headers.get("X-Twilio-Signature", "")):
            logger.warning("rejected Twilio status callback with a bad signature (org=%s)", contact.org_id)
            raise ForbiddenError("Invalid Twilio signature")
    elif not cfg.dry_run:
        raise ForbiddenError("Twilio credentials are not configured")
    await service.apply_status_callback(contact, params)
    return success_response()
