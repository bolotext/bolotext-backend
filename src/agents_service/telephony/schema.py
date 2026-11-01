import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_E164 = re.compile(r"^\+[1-9]\d{6,14}$")
_HOST = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.\-]*[A-Za-z0-9])?(:\d{1,5})?$")

Transport = Literal["auto", "udp", "tcp", "tls"]
Environment = Literal["development", "stage", "production"]


def _clean_numbers(v: list[str]) -> list[str]:
    out = []
    for n in v:
        n = re.sub(r"[\s\-()]", "", n.strip())
        if not _E164.match(n):
            raise ValueError(f"{n!r} is not an E.164 number (e.g. +919876543210)")
        if n not in out:
            out.append(n)
    return out


def _clean_host(v: str) -> str:
    v = v.strip().removeprefix("sip:").removeprefix("sips:").strip("/ ")
    if not _HOST.match(v):
        raise ValueError("Enter the provider's SIP host, e.g. mytrunk.pstn.twilio.com")
    return v


class TelephonyConnect(BaseModel):
    """What the provider (e.g. Twilio Elastic SIP Trunking) gives you. Saving it sets up **outbound** calling;
    inbound is switched on separately for Production (`POST /agents/{id}/telephony/inbound`)."""

    termination_uri: str = Field(description="The provider's termination SIP URI/host that LiveKit dials for outbound calls.")
    auth_username: str | None = Field(None, max_length=200, description="Provider credential-list username.")
    auth_password: str | None = Field(None, max_length=200, description="Provider credential-list password. Sent to LiveKit, never stored here; leave empty on update to keep the current one.")
    numbers: list[str] = Field(min_length=1, max_length=50, description="Numbers bought from the provider, E.164.")
    transport: Transport = "auto"

    _host = field_validator("termination_uri")(lambda cls, v: _clean_host(v))
    _nums = field_validator("numbers")(lambda cls, v: _clean_numbers(v))


class TelephonyOut(BaseModel):
    connected: bool
    origination_uri: str | None = Field(None, description="Give this to the provider as the origination (inbound) URI.")
    termination_uri: str | None = None
    auth_username: str | None = None
    numbers: list[str] = []
    outbound_enabled: bool = False
    inbound_enabled: bool = False
    inbound_numbers: list[str] = Field([], description="Numbers that receive inbound calls (the outbound numbers unless a different one was entered).")
    outbound_trunk_id: str | None = None
    outbound_trunk_shared: bool = Field(False, description="The outbound trunk was linked from an existing one (not created for this agent).")
    inbound_trunk_id: str | None = None
    dispatch_rule_id: str | None = None
    updated_at: datetime | None = None


class AvailableTrunk(BaseModel):
    """An existing outbound trunk this agent may link to."""

    id: str
    name: str
    address: str | None = None
    numbers: list[str] = []
    transport: str | None = None
    linked: bool = Field(False, description="This agent is already linked to it.")
    shared_with: int = Field(0, description="How many other agents already use this trunk.")
    usable: bool = Field(True, description="False when the trunk has no specific phone numbers to map calls to this agent.")


class UseTrunk(BaseModel):
    trunk_id: str = Field(min_length=1, max_length=100)


class EnableInbound(BaseModel):
    numbers: list[str] | None = Field(
        None,
        max_length=50,
        description="Numbers to receive inbound calls on, when they differ from the outbound numbers. Omit to use the outbound numbers.",
    )

    _nums = field_validator("numbers")(lambda cls, v: _clean_numbers(v) if v else None)


class TelephonyCall(BaseModel):
    phone_number: str = Field(description="Number to call, E.164.")
    environment: Environment = Field("development", description="Which environment's agent config this call uses; chosen per call.")
    consent_confirmed: bool = Field(description="The caller confirms the person called agreed to be called (TRAI/DPDP).")
    custom_variables: dict[str, str] = Field(default_factory=dict)

    _num = field_validator("phone_number")(lambda cls, v: _clean_numbers([v])[0])


class TelephonyCallOut(BaseModel):
    room_name: str
    sip_call_id: str


# ---- Super Admin: raw trunk management -------------------------------------


class TrunkOut(BaseModel):
    id: str
    kind: Literal["outbound", "inbound"]
    name: str
    address: str | None = None  # outbound: provider host
    numbers: list[str] = []
    auth_username: str | None = None
    allowed_addresses: list[str] = []  # inbound
    transport: str | None = None
    agent_id: str | None = Field(None, description="The agent this trunk was created for, if any.")


class DispatchRuleOut(BaseModel):
    id: str
    name: str
    trunk_ids: list[str] = []
    room_prefix: str | None = None
    metadata: str | None = None
    agent_id: str | None = None


class TrunkList(BaseModel):
    origination_uri: str | None = None
    outbound: list[TrunkOut]
    inbound: list[TrunkOut]
    dispatch_rules: list[DispatchRuleOut]


class TrunkIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    address: str | None = Field(None, description="Outbound only: provider SIP host.")
    numbers: list[str] = Field(default_factory=list, max_length=50)
    auth_username: str | None = None
    auth_password: str | None = None
    allowed_addresses: list[str] = Field(default_factory=list, description="Inbound only: provider IPs/CIDRs allowed to call in.")
    transport: Transport = "auto"

    _host = field_validator("address")(lambda cls, v: _clean_host(v) if v else v)
    _nums = field_validator("numbers")(lambda cls, v: _clean_numbers(v))


class RawTrunk(BaseModel):
    """A trunk exactly as LiveKit describes it (camelCase JSON, the same shape as the LiveKit dashboard's JSON editor)."""

    trunk: dict = Field(description="The trunk document. Read-only fields (sipTrunkId, createdAt, updatedAt) are ignored.")


class TrunkUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    address: str | None = None
    numbers: list[str] | None = None
    auth_username: str | None = None
    auth_password: str | None = None
    allowed_addresses: list[str] | None = None
    transport: Transport | None = None

    _host = field_validator("address")(lambda cls, v: _clean_host(v) if v else v)
    _nums = field_validator("numbers")(lambda cls, v: _clean_numbers(v) if v is not None else v)


# ---- Rent a number (LiveKit Phone Numbers) ---------------------------------


class NumberSearchResult(BaseModel):
    phone_number: str
    country_code: str | None = None
    area_code: str | None = None
    number_type: str = Field("unknown", description="local, toll_free, mobile or unknown")
    locality: str | None = None
    region: str | None = None
    capabilities: list[str] = []


class RentNumber(BaseModel):
    phone_number: str = Field(description="A number from the search results, E.164.")
    agent_id: str | None = Field(None, description="Connect the new number to this agent right away.")
    billing_confirmed: bool = Field(description="The caller understands LiveKit bills this number (including the full month if released early).")

    _num = field_validator("phone_number")(lambda cls, v: _clean_numbers([v])[0])


class AssignNumber(BaseModel):
    agent_id: str | None = Field(None, description="The agent that answers calls to the number; null disconnects it.")


class RentedNumberOut(BaseModel):
    id: str = Field(description="LiveKit's phone-number id.")
    phone_number: str
    number_type: str = "unknown"
    locality: str | None = None
    region: str | None = None
    status: str = "unknown"
    agent_id: str | None = None
    org_id: str | None = None
    org_name: str | None = None
    external: bool = Field(False, description="Already existed in LiveKit (rented outside this app); only a Super Admin sees it. Connecting it to an agent hands it to that agent's organization.")
    dispatch_rule_ids: list[str] = Field([], description="LiveKit dispatch rules the number is currently tied to (including ones made outside this app).")
    warning: str | None = None


class RentedNumberList(BaseModel):
    items: list[RentedNumberOut]
    limit_per_org: int | None = Field(None, description="Numbers an organization may hold; None for a Super Admin.")
