from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agents_service.core.partial import partial_model

HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]


class PostCallTriggerSettings(BaseModel):
    """A webhook the platform calls once a call ends (replaces the old bare
    `others.post_call_trigger_url` string) — same shape as dynamic_message's
    config, and for the same reason: storage/config only, actually calling
    it is a live-call-runtime concern outside this service.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "post_call_trigger_enabled": True,
                "method": "POST",
                "url": "https://example.com/webhooks/call-ended",
                "headers": {"Authorization": "Bearer xxx", "Content-Type": "application/json"},
            }
        }
    )

    post_call_trigger_enabled: bool = Field(False, description="Whether the webhook is called when a call ends.")
    method: HttpMethod = Field("POST", description="HTTP method used to call `url`.")
    url: str | None = Field(None, description="Endpoint called once a call ends.")
    headers: dict[str, str] = Field({}, description="Extra HTTP headers sent with the call-ended webhook request (e.g. an API key).")


PostCallTriggerSettingsUpdate = partial_model(PostCallTriggerSettings)
