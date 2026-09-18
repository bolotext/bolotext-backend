from pydantic import BaseModel, ConfigDict

from agents_service.core.partial import partial_model


class AgentDetails(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Loan Collections Agent",
                "description": "Outbound voice agent for early-bucket loan repayment reminders.",
                "languages": ["hi-IN", "en-IN"],
                "region": "asia",
                "timezone": "Asia/Kolkata",
                "bot_type": ["voice"],
            }
        }
    )

    name: str
    description: str | None = None
    languages: list[str] = ["en-IN"]
    region: str = "asia"
    timezone: str = "Asia/Kolkata"
    bot_type: list[str] = ["voice"]


AgentDetailsUpdate = partial_model(AgentDetails)
