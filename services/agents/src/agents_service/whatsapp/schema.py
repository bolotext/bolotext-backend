from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from agents_service.whatsapp.model import ApprovalStatus, Channel, FieldType, SendStatus, TemplateCategory, WhatsAppAgentStatus


class FieldIn(BaseModel):
    key: str = Field(..., min_length=1, max_length=40, description="Lowercase letters, digits, `_`; starts with a letter.")
    type: FieldType = "string"
    required: bool = False


class FieldOut(FieldIn):
    locked: bool = Field(False, description="Built-in field; can't be changed or removed.")


class FieldMapperUpdate(BaseModel):
    fields: list[FieldIn] = Field(default_factory=list, max_length=30, description="Custom fields (full_name and phone_number are always present).")


class WhatsAppAgentCreate(BaseModel):
    channel: Channel = Field("whatsapp", description="`whatsapp` or `sms`; fixed once created.")
    name: str = Field(..., min_length=1, max_length=100, description="Display name.")
    description: str | None = Field(None, max_length=500)
    use_case: str | None = Field(None, max_length=100, description="e.g. `payment-reminder`, `appointment`, `promo`.")
    twilio_sender: str | None = Field(
        None, max_length=40,
        description="Sender in E.164 (WhatsApp-enabled, or SMS-capable for SMS agents; SMS may also use a Messaging Service SID `MG…`). Empty = the org default.",
    )

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v


class WhatsAppAgentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    use_case: str | None = Field(None, max_length=100)
    twilio_sender: str | None = Field(None, max_length=40)
    status: WhatsAppAgentStatus | None = None


class WhatsAppAgentOut(BaseModel):
    id: str
    org_id: str | None
    user_id: str
    name: str
    description: str | None
    use_case: str | None
    twilio_sender: str | None
    channel: Channel
    status: WhatsAppAgentStatus
    field_mapper: list[FieldOut]
    created_at: datetime
    updated_at: datetime


class WhatsAppConfigOut(BaseModel):
    dry_run: bool = Field(description="True = messages are simulated, nothing reaches Twilio.")
    default_sender_configured: bool
    default_sms_sender_configured: bool = False


class TemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    language: str = Field("en", min_length=2, max_length=10, description="WhatsApp language code, e.g. `en`, `hi`, `en_US`.")
    category: TemplateCategory = "utility"
    body: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="Message text. Placeholders: `{{full_name}}`, `{{message}}` or any field-mapper key.",
    )


class TemplateUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    language: str | None = Field(None, min_length=2, max_length=10)
    category: TemplateCategory | None = None
    body: str | None = Field(None, min_length=1, max_length=1024)


class TemplateOut(BaseModel):
    id: str
    whatsapp_agent_id: str
    name: str
    language: str
    category: TemplateCategory
    body: str
    variables: list[str]
    var_names: list[str]
    source: Literal["bolotext", "twilio"]
    twilio_content_sid: str | None
    approval_status: ApprovalStatus
    rejection_reason: str | None
    created_at: datetime
    updated_at: datetime


class TwilioTemplateOut(BaseModel):
    """A Content template that exists in the Twilio account."""

    sid: str
    name: str
    language: str
    body: str
    variables: list[str] = Field(description="Twilio's variable names, e.g. `1`, `2`.")
    approval_status: str = Field(description="WhatsApp approval status as Twilio reports it (`unsubmitted` if never submitted).")
    category: str | None
    rejection_reason: str | None
    template_id: str | None = Field(description="Set when already linked to this agent.")


class TemplateImport(BaseModel):
    content_sid: str = Field(..., min_length=3, max_length=64, description="Twilio Content SID, e.g. `HX…`.")
    mapping: dict[str, str] = Field(default_factory=dict, description="Twilio variable name → contact field (`full_name`, `message` or a field-mapper key).")


class CsvUpload(BaseModel):
    filename: str = Field("contacts.csv", max_length=255)
    csv: str = Field(..., min_length=1, description="Raw CSV text with header `customer_name,phone_number,message`.")
    consent_confirmed: bool = Field(
        False, description="Uploader confirms these recipients have opted in to WhatsApp messages from the business."
    )


class RowError(BaseModel):
    row: int = Field(description="1-based CSV line number (header = 1).")
    error: str


class BatchOut(BaseModel):
    id: str
    whatsapp_agent_id: str
    filename: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    uploaded_by: str
    created_at: datetime


class UploadResult(BaseModel):
    batch: BatchOut
    errors: list[RowError]


class ContactCreate(BaseModel):
    customer_name: str = Field(..., min_length=1, max_length=200, description="The `full_name` field.")
    phone_number: str | int = Field(..., description="Any common format, or digits only; stored as an integer.")
    message: str = Field("", max_length=1600, description="Free text used when sending without a template.")
    data: dict[str, Any] = Field(default_factory=dict, description="Custom field values keyed by field-mapper key.")


class ContactUpdate(BaseModel):
    customer_name: str | None = Field(None, min_length=1, max_length=200)
    phone_number: str | int | None = None
    message: str | None = Field(None, max_length=1600)
    data: dict[str, Any] | None = None
    opted_out: bool | None = None


class ContactOut(BaseModel):
    id: str
    whatsapp_agent_id: str
    batch_id: str | None
    customer_name: str
    phone_number: int = Field(description="E.164 digits without `+`, e.g. 919876543210.")
    message: str
    data: dict[str, Any]
    send_status: SendStatus
    opted_out: bool
    template_id: str | None
    twilio_message_sid: str | None
    error: str | None
    sent_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MessageStatusOut(BaseModel):
    """One sent message with the actual status Twilio reported."""

    contact_id: str
    customer_name: str
    phone_number: int = Field(description="E.164 digits without `+`, e.g. 919876543210.")
    message_sid: str | None
    status: str | None = Field(None, description="Latest raw Twilio status; null if Twilio never accepted it.")
    send_status: SendStatus
    error_code: str | None
    error_message: str | None
    sent_at: datetime | None
    status_at: datetime | None
    events: int


class MessageStatusListOut(BaseModel):
    items: list[MessageStatusOut]
    total: int


class RefreshRequest(BaseModel):
    contact_ids: list[str] | None = Field(None, max_length=200, description="Only these contacts; default = every message still in flight.")


class RefreshResult(BaseModel):
    checked: int
    updated: int
    errors: int
    simulated: int = Field(description="Dry-run messages, which Twilio doesn't know about.")


class MessageEventOut(BaseModel):
    id: str
    message_sid: str | None
    status: str
    error_code: str | None
    error_message: str | None
    source: str
    payload: dict[str, str]
    received_at: datetime


class ContactListOut(BaseModel):
    items: list[ContactOut]
    total: int


class BulkDelete(BaseModel):
    contact_ids: list[str] = Field(..., min_length=1, max_length=5000)


class SendRequest(BaseModel):
    contact_ids: list[str] | None = Field(None, max_length=5000, description="Specific contacts to send to.")
    batch_id: str | None = Field(None, description="Or every sendable contact of this upload.")
    template_id: str | None = Field(
        None, description="Approved template to send. Omit to send each contact's own `message` as free text."
    )
    consent_confirmed: bool = Field(False, description="Must be true: recipients have opted in.")


class SendResult(BaseModel):
    job_id: str
    requested: int
    queued: int
    skipped: int = Field(description="Already sent/delivered, queued, opted out, or not found.")
    dry_run: bool


class StatsOut(BaseModel):
    total: int
    pending: int
    queued: int
    sent: int
    delivered: int
    read: int
    failed: int
    opted_out: int


class SettingsOut(BaseModel):
    """The org's Twilio settings. The auth token is write-only: only whether
    one is saved (and its last 4 characters) is ever returned.
    """

    twilio_account_sid: str
    has_auth_token: bool
    auth_token_hint: str | None = Field(None, description="`••••` + last 4 characters of the saved token.")
    twilio_whatsapp_from: str
    twilio_sms_from: str = ""
    dry_run: bool
    default_country_code: str
    simulated: bool = Field(description="True when messages are not really sent (dry-run, or credentials incomplete).")
    updated_at: datetime | None = None


class SettingsUpdate(BaseModel):
    """Partial update; omitted fields are unchanged, `\"\"` clears a text field."""

    twilio_account_sid: str | None = Field(None, max_length=64, description="Twilio Account SID (`AC…`).")
    auth_token: str | None = Field(None, max_length=128, description="New auth token. Omit or send empty to keep the saved one.")
    twilio_whatsapp_from: str | None = Field(None, max_length=32, description="Default WhatsApp-enabled sender (E.164).")
    twilio_sms_from: str | None = Field(None, max_length=40, description="Default SMS sender: a Twilio number (E.164) or a Messaging Service SID (`MG…`).")
    dry_run: bool | None = None
    default_country_code: str | None = Field(None, max_length=4, description="Prefix for bare 10-digit numbers, e.g. `91`.")


class ConnectionTestOut(BaseModel):
    ok: bool
    detail: str
