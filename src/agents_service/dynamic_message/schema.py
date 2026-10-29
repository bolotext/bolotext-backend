from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agents_service.core.partial import partial_model

HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]


class DynamicMessageSettings(BaseModel):
    """An external API the agent can call mid-conversation for a dynamic
    message (e.g. fetching a live order status to speak back to the
    caller). Calling it is a live-call-runtime concern, outside this
    service — this section is only ever configuration/storage.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "dynamic_message_enabled": True,
                "method": "POST",
                "url": "https://example.com/api",
                "headers": {"Authorization": "Bearer xxx", "Content-Type": "application/json"},
            }
        }
    )

    dynamic_message_enabled: bool = Field(False, description="Whether this agent may fetch and speak a dynamic message mid-call.")
    method: HttpMethod = Field("POST", description="HTTP method used to call `url`.")
    url: str | None = Field(None, description="Endpoint called to fetch the dynamic message content.")
    headers: dict[str, str] = Field({}, description="Extra HTTP headers sent with every call to `url` (e.g. an API key).")


DynamicMessageSettingsUpdate = partial_model(DynamicMessageSettings)
