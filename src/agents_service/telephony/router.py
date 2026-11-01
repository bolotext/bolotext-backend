from typing import Literal

from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends, Path

from agents_service.core.deps import AuthContext, get_current_auth
from agents_service.telephony import service
from agents_service.telephony.schema import (
    AvailableTrunk,
    EnableInbound,
    RawTrunk,
    TelephonyCall,
    TelephonyCallOut,
    TelephonyConnect,
    TelephonyOut,
    TrunkIn,
    TrunkList,
    TrunkOut,
    TrunkUpdate,
    UseTrunk,
)
from agents_service.usage.router import require_super_admin

router = APIRouter(prefix="/agents", tags=["agents:telephony"])
admin_router = APIRouter(prefix="/admin/telephony", tags=["admin:telephony"])

_AGENT_ID = Path(description="The agent's id.")


@router.get("/{agent_id}/telephony", response_model=SuccessResponse[TelephonyOut], summary="An agent's telephony connection")
async def get_telephony(agent_id: PydanticObjectId = _AGENT_ID, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """The saved connection plus the **origination SIP URI** to give the provider.
    **Auth:** anyone who can view the agent."""
    return success_response(data=await service.get(agent_id, auth))


@router.put("/{agent_id}/telephony", response_model=SuccessResponse[TelephonyOut], summary="Connect an agent to a SIP provider")
async def connect_telephony(payload: TelephonyConnect, agent_id: PydanticObjectId = _AGENT_ID, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Creates or updates the LiveKit **outbound** trunk (termination URI + credentials + numbers) and
    saves the numbers. Inbound is a separate step (`POST .../telephony/inbound`, Production). If inbound is
    already on, its trunk numbers are kept in step.
    **Auth:** anyone who can edit the agent. **Errors:** `BAD_REQUEST` with LiveKit's message."""
    return success_response(message="Telephony connected", data=await service.connect(agent_id, auth, payload))


@router.get("/{agent_id}/telephony/trunks", response_model=SuccessResponse[list[AvailableTrunk]], summary="Existing outbound trunks this agent can link to")
async def available_trunks(agent_id: PydanticObjectId = _AGENT_ID, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Outbound trunks this agent may link to: the shared pool a Super Admin maintains, plus trunks set up for other
    agents **of the same organization** (a trunk can serve several agents; `shared_with` says how many already do).
    Another organization's trunks are never listed. **Auth:** anyone who can view the agent."""
    return success_response(data=await service.list_available_trunks(agent_id, auth))


@router.post("/{agent_id}/telephony/use-trunk", response_model=SuccessResponse[TelephonyOut], summary="Connect an agent to an existing outbound trunk")
async def use_trunk(payload: UseTrunk, agent_id: PydanticObjectId = _AGENT_ID, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Links the agent to `trunk_id` instead of creating a trunk. The trunk's numbers become the agent's numbers.
    The trunk is shared, so it is never edited or deleted from here. **Auth:** anyone who can edit the agent.
    **Errors:** `BAD_REQUEST` (trunk not available to this agent, or no specific numbers), `CONFLICT` (inbound is on and a
    number already answers inbound for another agent), `NOT_FOUND`."""
    return success_response(message="Connected to the trunk", data=await service.use_existing_trunk(agent_id, auth, payload.trunk_id))


@router.post("/{agent_id}/telephony/inbound", response_model=SuccessResponse[TelephonyOut], summary="Enable inbound calls (Production)")
async def enable_inbound(
    payload: EnableInbound | None = None,
    agent_id: PydanticObjectId = _AGENT_ID,
    auth: AuthContext = Depends(get_current_auth),
) -> dict:
    """Creates the inbound trunk and dispatch rule so calls are answered by this agent's **Production** config.
    By default it uses the numbers saved by `PUT .../telephony`. If one of them already receives inbound calls for
    another agent the call fails with `CONFLICT`; retry with `numbers` set to a different inbound number.
    **Errors:** `BAD_REQUEST` if the provider details were never saved, or the agent has no Production config yet;
    `CONFLICT` when a number already answers inbound for another agent."""
    data = await service.enable_inbound(agent_id, auth, payload.numbers if payload else None)
    return success_response(message="Inbound calls enabled", data=data)


@router.delete("/{agent_id}/telephony/inbound", response_model=SuccessResponse[TelephonyOut], summary="Disable inbound calls")
async def disable_inbound(agent_id: PydanticObjectId = _AGENT_ID, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Removes the inbound trunk and dispatch rule; outbound calling is unaffected."""
    return success_response(message="Inbound calls disabled", data=await service.disable_inbound(agent_id, auth))


@router.delete("/{agent_id}/telephony", response_model=SuccessResponse[TelephonyOut], summary="Remove an agent's telephony connection")
async def disconnect_telephony(agent_id: PydanticObjectId = _AGENT_ID, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Deletes this agent's trunks and dispatch rule from LiveKit. **Auth:** anyone who can edit the agent."""
    return success_response(message="Telephony disconnected", data=await service.disconnect(agent_id, auth))


@router.post("/{agent_id}/telephony/call", response_model=SuccessResponse[TelephonyCallOut], summary="Place a test outbound phone call")
async def telephony_call(payload: TelephonyCall, agent_id: PydanticObjectId = _AGENT_ID, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Dispatches the agent to dial `phone_number` through the connected outbound trunk.
    The person called must have consented; Indian numbers fall under TRAI consent/DND rules [TO CONFIRM with Compliance]."""
    if not payload.consent_confirmed:
        from common.errors import BadRequestError

        raise BadRequestError("Confirm that the person being called has consented")
    return success_response(message="Call started", data=await service.place_call(agent_id, auth, payload))


# ------------------------------------------------------------ Super Admin CRUD


@admin_router.get("/trunks", response_model=SuccessResponse[TrunkList], summary="All SIP trunks and dispatch rules in LiveKit")
async def list_trunks(_: AuthContext = Depends(require_super_admin)) -> dict:
    """Outbound trunks, inbound trunks and dispatch rules of the whole LiveKit project (passwords are never returned). Super Admin only."""
    return success_response(data=await service.list_trunks())


@admin_router.post("/trunks/{kind}", response_model=SuccessResponse[TrunkOut], summary="Create an outbound or inbound trunk")
async def create_trunk(kind: Literal["outbound", "inbound"], payload: TrunkIn, _: AuthContext = Depends(require_super_admin)) -> dict:
    return success_response(message="Trunk created", data=await service.create_trunk(kind, payload))


@admin_router.patch("/trunks/{kind}/{trunk_id}", response_model=SuccessResponse[TrunkOut], summary="Update a trunk")
async def update_trunk(kind: Literal["outbound", "inbound"], trunk_id: str, payload: TrunkUpdate, _: AuthContext = Depends(require_super_admin)) -> dict:
    """Only the fields sent are changed; an empty `auth_password` keeps the current one."""
    return success_response(message="Trunk updated", data=await service.update_trunk(kind, trunk_id, payload))


@admin_router.get("/trunks/{kind}/{trunk_id}/raw", response_model=SuccessResponse[RawTrunk], summary="A trunk as LiveKit JSON (for the JSON editor)")
async def get_trunk_raw(kind: Literal["outbound", "inbound"], trunk_id: str, _: AuthContext = Depends(require_super_admin)) -> dict:
    """Every field of the trunk as camelCase JSON, like the LiveKit dashboard: defaults included, read-only id and timestamps
    included (ignored on save), password never included. Super Admin only."""
    return success_response(data={"trunk": await service.get_trunk_raw(kind, trunk_id)})


@admin_router.put("/trunks/{kind}/{trunk_id}/raw", response_model=SuccessResponse[TrunkOut], summary="Replace a trunk from edited JSON")
async def put_trunk_raw(kind: Literal["outbound", "inbound"], trunk_id: str, payload: RawTrunk, _: AuthContext = Depends(require_super_admin)) -> dict:
    """Replaces the trunk with the JSON (omitted fields are cleared). `authPassword` may be omitted to keep the saved one.
    **Errors:** `UNPROCESSABLE_ENTITY` for unknown fields or wrong types, `BAD_REQUEST` if a password is required."""
    return success_response(message="Trunk updated", data=await service.replace_trunk_raw(kind, trunk_id, payload.trunk))


@admin_router.delete("/trunks/{kind}/{trunk_id}", response_model=SuccessResponse[dict], summary="Delete a trunk or dispatch rule")
async def delete_trunk(kind: Literal["outbound", "inbound", "dispatch-rule"], trunk_id: str, _: AuthContext = Depends(require_super_admin)) -> dict:
    await service.delete_trunk(kind, trunk_id)
    return success_response(message="Deleted", data={"id": trunk_id})
