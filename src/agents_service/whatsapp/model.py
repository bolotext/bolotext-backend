from datetime import datetime, timezone
from typing import Any, Literal

from beanie import Document
from pydantic import BaseModel, Field
from pymongo import IndexModel

WhatsAppAgentStatus = Literal["active", "inactive"]
Channel = Literal["whatsapp", "sms"]
TemplateCategory = Literal["utility", "marketing", "authentication"]
ApprovalStatus = Literal["draft", "pending", "approved", "rejected"]
FieldType = Literal["string", "number", "long", "boolean", "checkbox", "date"]
SendStatus = Literal["pending", "queued", "sent", "delivered", "read", "failed"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FieldDef(BaseModel):
    """A custom column of the agent's upload data (key + MongoDB data type)."""

    key: str
    type: FieldType = "string"
    required: bool = False


class WhatsAppSettings(Document):
    """Per-organization Twilio configuration, one document per org. The auth
    token is stored Fernet-encrypted and is never returned by any endpoint.
    """

    org_id: str
    twilio_account_sid: str = ""
    twilio_auth_token_enc: str = ""
    twilio_auth_token_last4: str = ""
    twilio_whatsapp_from: str = ""
    twilio_sms_from: str = ""  # SMS-capable number, or a Messaging Service SID (MG…)
    # Safe default: simulate everything until an admin turns real sending on.
    dry_run: bool = True
    default_country_code: str = "91"
    updated_by: str | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "whatsapp_settings"
        indexes = [IndexModel("org_id", unique=True)]


class WhatsAppAgent(Document):
    """A messaging "agent" for one outbound use case (e.g. payment reminders).
    Separate from the voice/chat `Agent` — it owns templates and contacts, and
    sends through a WhatsApp-enabled Twilio sender.
    """

    org_id: str | None = None
    user_id: str
    name: str
    description: str | None = None
    use_case: str | None = None
    # E.164 WhatsApp-enabled number; falls back to the org's default sender.
    twilio_sender: str | None = None
    # Same module serves both channels: an SMS agent sends plain text and needs no approved templates.
    channel: Channel = "whatsapp"
    status: WhatsAppAgentStatus = "active"
    # Extra upload columns beyond the built-in full_name / phone_number.
    custom_fields: list[FieldDef] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "whatsapp_agents"
        indexes = [IndexModel("org_id"), IndexModel("user_id")]


class WhatsAppTemplate(Document):
    """A WhatsApp message template. `body` uses `{{customer_name}}` /
    `{{message}}` placeholders; they're mapped to Twilio's numeric `{{1}}`
    variables on submit (see service.to_twilio_body).
    """

    org_id: str | None = None
    whatsapp_agent_id: str
    name: str
    language: str = "en"
    category: TemplateCategory = "utility"
    body: str
    variables: list[str] = Field(default_factory=list)
    twilio_content_sid: str | None = None
    approval_status: ApprovalStatus = "draft"
    rejection_reason: str | None = None
    # "bolotext": created here and submitted to Twilio by us. "twilio": created on the
    # Twilio platform and linked here; it stays managed (and editable) in Twilio.
    source: Literal["bolotext", "twilio"] = "bolotext"
    # Twilio's own variable names for the content ("1", "2", …); `variables[i]` is the
    # contact field that fills `var_names[i]`. Empty = numeric 1..n.
    var_names: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "whatsapp_templates"
        indexes = [IndexModel("whatsapp_agent_id"), IndexModel("twilio_content_sid")]


class WhatsAppBatch(Document):
    """One CSV upload."""

    org_id: str | None = None
    whatsapp_agent_id: str
    filename: str
    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    uploaded_by: str
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "whatsapp_batches"
        indexes = [IndexModel("whatsapp_agent_id")]


class WhatsAppContact(Document):
    """One recipient row (customer_name, phone_number, message) of an agent."""

    org_id: str | None = None
    whatsapp_agent_id: str
    batch_id: str | None = None
    customer_name: str
    phone_number: int  # E.164 digits without the `+` (e.g. 919876543210), stored as a MongoDB long
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)  # custom fields, typed per the agent's mapper
    send_status: SendStatus = "pending"
    opted_out: bool = False
    send_job_id: str | None = None
    queued_at: datetime | None = None
    template_id: str | None = None
    twilio_message_sid: str | None = None
    error: str | None = None
    sent_at: datetime | None = None
    # Latest raw status Twilio reported (accepted/queued/sending/sent/delivered/read/
    # undelivered/failed); `send_status` above is the simplified UI status.
    twilio_status: str | None = None
    twilio_status_at: datetime | None = None
    twilio_error_code: str | None = None
    twilio_error_message: str | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "whatsapp_contacts"
        indexes = [
            IndexModel("whatsapp_agent_id"),
            IndexModel("batch_id"),
            IndexModel("send_status"),
            IndexModel("twilio_message_sid"),
            IndexModel("send_job_id"),
        ]


class WhatsAppMessageEvent(Document):
    """Append-only log of every status Twilio reported for a message — the full
    callback payload is kept verbatim in `payload`."""

    org_id: str | None = None
    whatsapp_agent_id: str
    contact_id: str
    message_sid: str | None = None
    status: str  # raw Twilio status, lowercase
    error_code: str | None = None
    error_message: str | None = None
    source: Literal["send", "webhook", "refresh"] = "webhook"  # refresh = fetched from Twilio on demand
    payload: dict[str, str] = Field(default_factory=dict)
    received_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "whatsapp_message_events"
        indexes = [IndexModel("contact_id"), IndexModel("whatsapp_agent_id"), IndexModel("message_sid")]
