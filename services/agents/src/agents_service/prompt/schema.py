from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from agents_service.core.partial import partial_model


class AgentPrompt(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "welcome_message": "Hi {{customer_name}}, this is Neha calling from [BANK_A] regarding your loan account.",
                "system_prompt": "You are a polite, firm collections agent. Confirm identity, state the outstanding amount ({{due_amount}}), and offer a payment link.",
                "ending_message": "Thank you for your time, {{customer_name}}. Have a great day.",
                "dynamic_variables": ["customer_name", "due_amount"],
                "language_specific_prompts": {"hi-IN": "आप एक विनम्र वसूली एजेंट हैं..."},
                "language_switch_mode": "explicit",
                "language_switch_prompt": None,
                "min_words_for_lang_switch": 2,
            }
        }
    )

    # Left as "" (not a bare required str) so `POST /agents` can default-construct
    # this section with just `agent_details.name` supplied — see agents/service.py.
    welcome_message: str = ""
    system_prompt: str = ""
    ending_message: str = ""
    dynamic_variables: list[str] = []
    language_specific_prompts: dict[str, str] = {}
    language_switch_mode: Literal["implicit", "explicit", "custom"] = "explicit"
    language_switch_prompt: str | None = None
    min_words_for_lang_switch: int = 2


AgentPromptUpdate = partial_model(AgentPrompt)


class TestRenderRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"sample_values": {"customer_name": "Ramesh Kumar"}}})

    sample_values: dict[str, str] = {}


class TestRenderResponse(BaseModel):
    welcome_message: str
    system_prompt: str
    ending_message: str
    sample_values_used: dict[str, str]


class SystemPromptVersionOut(BaseModel):
    version: int
    system_prompt: str
    created_by: str
    created_at: datetime
