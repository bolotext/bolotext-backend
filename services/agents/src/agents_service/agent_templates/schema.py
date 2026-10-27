from pydantic import BaseModel, ConfigDict, Field

from agents_service.faq.schema import FAQPair

TEMPLATE_DISCLAIMER = (
    "Starter draft only. Review and adapt it to your business, and get Legal/Compliance sign-off "
    "before using it in production."
)


class AgentTemplate(BaseModel):
    """A ready-made starting point for an agent: prompt text, pre-call
    variables, FAQ and languages pre-filled for one use case. Defined in code
    (see data.py) and versioned with the service — creating an agent from a
    template copies it, so later template edits never change existing agents.
    """

    key: str = Field(description="Stable identifier used in the API path, e.g. `appointment-booking`.")
    name: str = Field(description="Default agent name when created from this template.")
    category: str = Field(description="Use-case category, e.g. `Healthcare`, `Insurance`, `Lending`.")
    description: str = Field(description="One-line summary of what the agent does.")
    direction: str = Field(description='"inbound", "outbound" or "both" — how calls typically reach this agent.')
    languages: list[str] = Field(description="Language codes the template is configured with.")
    regulatory_notes: list[str] = Field(
        description="Regimes/guidelines to review before production. Pointers for Legal/Compliance, not legal advice."
    )
    pre_call_variables: dict[str, str] = Field(
        description="Declared `{{variable}}` names and sample defaults. Overridden per call by your dialer/CRM."
    )
    welcome_message: str
    system_prompt: str
    ending_message: str
    faq: list[FAQPair] = Field(default_factory=list)


class AgentTemplateSummary(BaseModel):
    key: str = Field(description="Stable identifier used in the API path.")
    name: str
    category: str
    description: str
    direction: str
    languages: list[str]


class AgentTemplateOut(AgentTemplate):
    model_config = ConfigDict(json_schema_extra={"example": {"key": "appointment-booking"}})

    disclaimer: str = Field(TEMPLATE_DISCLAIMER, description="Reminder that templates are drafts needing review.")


class AgentFromTemplateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"name": "Clinic Booking Agent", "description": "Books OPD appointments."}}
    )

    name: str | None = Field(None, min_length=1, max_length=200, description="Agent name; defaults to the template's name.")
    description: str | None = Field(None, description="Agent description; defaults to the template's description.")
