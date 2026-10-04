from pydantic import BaseModel, ConfigDict, Field

from agents_service.core.partial import partial_model


class DeploymentSettings(BaseModel):
    """Which channels an agent is reachable on, and where its chat widget
    may be embedded."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "inbound_calling_enabled": False,
                "inbound_number": None,
                "outbound_calling_enabled": True,
                "chat_widget_enabled": True,
                "valid_origins": ["https://app.example.com"],
            }
        }
    )

    inbound_calling_enabled: bool = Field(False, description="Whether this agent answers inbound calls.")
    inbound_number: str | None = Field(None, description="Phone number this agent answers inbound calls on, if inbound calling is enabled.")
    outbound_calling_enabled: bool = Field(True, description="Whether this agent can be used to place outbound calls.")
    chat_widget_enabled: bool = Field(False, description="Whether this agent is reachable via the embeddable chat widget.")
    valid_origins: list[str] = Field([], description="Origins (e.g. https://app.example.com) allowed to embed the chat widget; empty allows none.")
    # embedding_script is derived server-side from agent_id, not stored here.


DeploymentSettingsUpdate = partial_model(DeploymentSettings)
