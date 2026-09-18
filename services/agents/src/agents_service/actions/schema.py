from typing import Literal

from pydantic import BaseModel, ConfigDict

from agents_service.core.partial import partial_model


class ActionParam(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "slot_id",
                "type": "string",
                "description": "The identifier of the slot to reserve.",
                "required": True,
            }
        }
    )

    name: str
    type: Literal["string", "number", "boolean"]
    description: str
    required: bool = True


class AgentAction(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "reserve_slot",
                "description": "Reserves an appointment slot for the customer.",
                "endpoint_url": "https://example.com/api/slots/reserve",
                "method": "POST",
                "params": [
                    {"name": "slot_id", "type": "string", "description": "Slot to reserve.", "required": True}
                ],
                "headers": {"Authorization": "Bearer [REDACTED]"},
            }
        }
    )

    name: str
    description: str
    endpoint_url: str
    method: Literal["GET", "POST"] = "POST"
    params: list[ActionParam] = []
    headers: dict[str, str] = {}


class ActionsSettings(BaseModel):
    actions: list[AgentAction] = []


ActionsSettingsUpdate = partial_model(ActionsSettings)
