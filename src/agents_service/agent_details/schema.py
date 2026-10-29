from pydantic import BaseModel, ConfigDict, Field

from agents_service.core.partial import partial_model


class AgentDetails(BaseModel):
    """Identity/basics section of the agent builder. Also the request body
    for `POST /agents` (paired there with defaults for every other section).
    """

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
    name: str = Field(description="The agent's display name.")
    description: str | None = Field(None, description="Optional free-text description of the agent's purpose.")
    region: str = Field("asia", description="Deployment region the agent runs in.")
    timezone: str = Field("Asia/Kolkata", description="IANA timezone used for scheduling/time-sensitive behavior.")
    bot_type: list[str] = Field(["voice"], description='Channels this agent operates on, e.g. `["voice"]`, `["chat"]`.')


AgentDetailsUpdate = partial_model(AgentDetails)
