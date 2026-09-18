from typing import Literal

from pydantic import BaseModel, ConfigDict

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

    dynamic_message_enabled: bool = False
    method: HttpMethod = "POST"
    url: str | None = None
    headers: dict[str, str] = {}


DynamicMessageSettingsUpdate = partial_model(DynamicMessageSettings)
