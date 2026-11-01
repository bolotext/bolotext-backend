from datetime import datetime, timezone

from beanie import Document
from pydantic import Field
from pymongo import IndexModel


class TelephonyConnection(Document):
    """Which LiveKit SIP trunks / dispatch rule serve one agent. LiveKit is the source of
    truth for the trunks themselves; this only remembers the ids so we can update or remove
    them later. The provider auth password is never stored here (LiveKit keeps it)."""

    agent_id: str
    org_id: str | None = None
    termination_uri: str  # provider SIP host calls are sent to (outbound)
    auth_username: str | None = None
    numbers: list[str] = Field(default_factory=list)  # E.164 numbers bought from the provider
    outbound_enabled: bool = True
    inbound_enabled: bool = False  # switched on separately, for Production
    # Numbers that receive inbound calls when they differ from `numbers` (e.g. the outbound number already answers
    # inbound for another agent). Empty = inbound uses `numbers`.
    inbound_numbers: list[str] = Field(default_factory=list)
    outbound_trunk_id: str | None = None
    # True when the outbound trunk was picked from the existing ones rather than created for this agent; it is
    # shared, so we never edit or delete it from here.
    outbound_trunk_shared: bool = False
    inbound_trunk_id: str | None = None
    dispatch_rule_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "telephony_connections"
        indexes = [IndexModel("agent_id", unique=True), IndexModel("org_id")]


class RentedNumber(Document):
    """A phone number rented from LiveKit Phone Numbers through this app. LiveKit holds the number; this remembers which
    organization rented it and which agent answers it, so an Admin only ever sees and changes their own."""

    livekit_id: str  # LiveKit's phone-number id
    phone_number: str  # E.164
    org_id: str | None = None  # None until a Super Admin connects an unclaimed number to an agent
    agent_id: str | None = None
    dispatch_rule_id: str | None = None  # the rule we created for it (removed when the number is released/disconnected)
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "rented_numbers"
        indexes = [IndexModel("livekit_id", unique=True), IndexModel("phone_number", unique=True), IndexModel("org_id")]
