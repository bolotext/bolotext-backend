from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agents_service.core.partial import partial_model


class ActionParam(BaseModel):
    """One parameter the LLM must supply when it invokes an `AgentAction`."""

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

    name: str = Field(..., description="Parameter name, as passed to the action's endpoint.")
    type: Literal["string", "number", "boolean"] = Field(..., description="Expected JSON type of the parameter's value.")
    description: str = Field(..., description="Explains the parameter to the LLM so it can fill it in correctly.")
    required: bool = Field(True, description="Whether the LLM must supply this parameter before the action can be called.")


class AgentAction(BaseModel):
    """A custom HTTP callout the agent's LLM can invoke mid-call (a
    function/tool call), e.g. to reserve a slot or look up an account.
    Calling it is a live-call-runtime concern — this service only stores
    the definition.
    """

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

    name: str = Field(..., description="Unique action name the LLM uses to call this tool.")
    description: str = Field(..., description="Explains to the LLM what this action does and when to call it.")
    endpoint_url: str = Field(..., description="HTTP endpoint invoked when the LLM calls this action.")
    method: Literal["GET", "POST"] = Field("POST", description="HTTP method used to call the endpoint.")
    params: list[ActionParam] = Field([], description="Parameters the LLM must supply when calling this action.")
    headers: dict[str, str] = Field({}, description="Extra HTTP headers sent with every call to this action's endpoint (e.g. an API key).")


class ActionsSettings(BaseModel):
    actions: list[AgentAction] = Field([], description="Custom actions/tools available to this agent during a call.")


ActionsSettingsUpdate = partial_model(ActionsSettings)
