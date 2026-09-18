from typing import Literal

from pydantic import BaseModel, ConfigDict

from agents_service.core.partial import partial_model


class AgentFlow(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "agent_type": "single_prompt",
                "drop_off_scenarios": ["customer_hung_up", "requested_human_agent"],
                "flow_definition": None,
            }
        }
    )

    agent_type: Literal["single_prompt", "flow"] = "single_prompt"
    drop_off_scenarios: list[str] = []
    flow_definition: dict | None = None


AgentFlowUpdate = partial_model(AgentFlow)
