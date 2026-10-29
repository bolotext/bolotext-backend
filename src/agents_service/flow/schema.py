from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agents_service.core.partial import partial_model


class AgentFlow(BaseModel):
    """Conversation flow configuration for an agent."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "agent_type": "single_prompt",
                "drop_off_scenarios": ["customer_hung_up", "requested_human_agent"],
                "flow_definition": None,
            }
        }
    )

    agent_type: Literal["single_prompt", "flow"] = Field(
        "single_prompt",
        description='"single_prompt" drives the whole call from `prompt.system_prompt` alone; '
        '"flow" follows a structured, multi-step `flow_definition` instead.',
    )
    drop_off_scenarios: list[str] = Field(
        [], description="Named scenarios (e.g. `customer_hung_up`, `requested_human_agent`) that end the call early."
    )
    flow_definition: dict | None = Field(
        None, description='Structured flow graph, used only when `agent_type` is "flow"; `null` otherwise.'
    )


AgentFlowUpdate = partial_model(AgentFlow)
