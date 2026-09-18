from pydantic import BaseModel, ConfigDict

from agents_service.core.partial import partial_model


class AgentDetails(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Loan Collections Agent",
                "description": "Outbound voice agent for early-bucket loan repayment reminders.",
                "region": "asia",
                "timezone": "Asia/Kolkata",
                "bot_type": ["voice"],
            }
        }
    )

    # Deliberately not here: an agent is created English-only (AgentConfig.languages
    # defaults to ["en-IN"]) and languages are configured afterwards, only through
    # the dedicated PUT /agents/{id}/languages — see agents_service.languages.
    name: str
    description: str | None = None
    region: str = "asia"
    timezone: str = "Asia/Kolkata"
    bot_type: list[str] = ["voice"]


AgentDetailsUpdate = partial_model(AgentDetails)
