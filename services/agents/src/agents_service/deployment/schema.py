from pydantic import BaseModel, ConfigDict

from agents_service.core.partial import partial_model


class DeploymentSettings(BaseModel):
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

    inbound_calling_enabled: bool = False
    inbound_number: str | None = None
    outbound_calling_enabled: bool = True
    chat_widget_enabled: bool = False
    valid_origins: list[str] = []
    # embedding_script is derived server-side from agent_id, not stored here.


DeploymentSettingsUpdate = partial_model(DeploymentSettings)
