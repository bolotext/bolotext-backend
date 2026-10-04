from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from agents_service.actions.schema import ActionsSettings, ActionsSettingsUpdate
from agents_service.agent_configs.model import Environment
from agents_service.agent_details.schema import AgentDetails
from agents_service.agents.model import AgentStatus
from agents_service.analytics.schema import AnalyticsSettings, AnalyticsSettingsUpdate
from agents_service.deployment.schema import DeploymentSettings, DeploymentSettingsUpdate
from agents_service.faq.schema import FAQSettings, FAQSettingsUpdate
from agents_service.flow.schema import AgentFlow, AgentFlowUpdate
from agents_service.llm.schema import LLMSettings, LLMSettingsUpdate
from agents_service.mcp.schema import MCPSettings, MCPSettingsUpdate
from agents_service.others.schema import OthersSettings, OthersSettingsUpdate
from agents_service.prompt.schema import AgentPrompt, AgentPromptUpdate
from agents_service.transcriber.schema import TranscriberSettings, TranscriberSettingsUpdate
from agents_service.voice_persona.schema import VoicePersonaSection, VoicePersonaSectionUpdate


@dataclass(frozen=True)
class SectionSpec:
    attr: str  # attribute name on the AgentConfig document
    full_model: type[BaseModel]  # the section's canonical (fully-specified) shape
    update_model: type[BaseModel]  # every field optional, for PATCH


# URL path segment (as used in PATCH /agents/{agent_id}/{section}, one per
# tab's own router) -> spec. `agent-details` isn't here: it's the one tab
# split across both documents (name/description on Agent, the rest on
# AgentConfig), so it's handled directly by agents.service.update_agent_details
# instead of this generic, single-document dispatch table.
SECTIONS: dict[str, SectionSpec] = {
    "prompt": SectionSpec("prompt", AgentPrompt, AgentPromptUpdate),
    "flow": SectionSpec("flow", AgentFlow, AgentFlowUpdate),
    "transcriber": SectionSpec("transcriber", TranscriberSettings, TranscriberSettingsUpdate),
    "llm": SectionSpec("llm", LLMSettings, LLMSettingsUpdate),
    "voice-persona": SectionSpec("voice_persona", VoicePersonaSection, VoicePersonaSectionUpdate),
    "analytics": SectionSpec("analytics", AnalyticsSettings, AnalyticsSettingsUpdate),
    "others": SectionSpec("others", OthersSettings, OthersSettingsUpdate),
    "faq": SectionSpec("faq", FAQSettings, FAQSettingsUpdate),
    "deployment": SectionSpec("deployment", DeploymentSettings, DeploymentSettingsUpdate),
    "actions": SectionSpec("actions", ActionsSettings, ActionsSettingsUpdate),
    "mcp": SectionSpec("mcp", MCPSettings, MCPSettingsUpdate),
}


class AgentOut(BaseModel):
    """The API's merged, per-tab view of an agent — unchanged externally even
    though storage now spans two collections (Agent + AgentConfig): the
    tabbed builder UI shouldn't need to know or care about that split.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="The agent's id.")
    user_id: str = Field(description="Id of the user who owns this agent.")
    org_id: str | None = Field(description="Id of the owning organization, or `null` for a personal (non-org) agent.")
    status: AgentStatus = Field(description='Whether the agent can currently be used: "active" or "inactive".')
    environment: Environment = Field(
        description='Which environment this snapshot is: "development" (live, directly editable), '
        '"stage", or "production" (both read-only, written only by promotion).'
    )
    # Not on AgentDetails: it's created English-only and configured afterwards
    # only through PUT /agents/{id}/languages — see agents_service.languages.
    languages: list[str] = Field(description="Configured language codes (e.g. `en-IN`, `hi-IN`) the agent can speak.")
    agent_details: AgentDetails = Field(description="Identity/basics: name, description, region, timezone, bot type.")
    prompt: AgentPrompt = Field(description="System prompt content, messages, language-switch behavior, and dynamic message settings.")
    flow: AgentFlow = Field(description="Conversation flow configuration.")
    transcriber: TranscriberSettings = Field(description="Speech-to-text (ASR) provider and tuning settings.")
    llm: LLMSettings = Field(description="LLM provider and generation settings.")
    voice_persona: VoicePersonaSection = Field(description="Text-to-speech voice and persona settings.")
    analytics: AnalyticsSettings = Field(description="Call analytics configuration, including the post-call trigger webhook.")
    others: OthersSettings = Field(description="Miscellaneous settings that don't belong to a dedicated tab.")
    faq: FAQSettings = Field(description="FAQ entries the agent can draw on during a call.")
    deployment: DeploymentSettings = Field(description="Deployment/channel settings for publishing the agent.")
    actions: ActionsSettings = Field(description="Custom actions/functions the agent can invoke during a call.")
    mcp: MCPSettings = Field(description="Model Context Protocol server integrations available to the agent.")
    created_at: datetime = Field(description="When the agent was created (UTC).")
    updated_at: datetime = Field(description="When this environment snapshot was last updated (UTC).")


class AgentIdentitySummary(BaseModel):
    """The subset of "Agent Details" that lives on the Agent identity
    document itself (see agents/model.py) — used only by AgentListItem below,
    which deliberately excludes everything AgentConfig owns (region/
    timezone/bot_type/languages/environment, and every builder-tab section).
    """

    name: str = Field(description="The agent's display name.")
    description: str | None = Field(None, description="Optional free-text description of the agent's purpose.")


class AgentListItem(BaseModel):
    """One row of GET /agents. Unlike AgentOut, this never touches
    AgentConfig at all — no builder-tab sections, no environment/languages/
    region/timezone/bot_type — just the Agent identity document's own
    fields, so listing agents doesn't cost one AgentConfig read per agent for
    data a list view doesn't need. Fetch GET /agents/{id} for the full
    merged view.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="The agent's id.")
    user_id: str = Field(description="Id of the user who owns this agent.")
    org_id: str | None = Field(description="Id of the owning organization, or `null` for a personal (non-org) agent.")
    status: AgentStatus = Field(description='Whether the agent can currently be used: "active" or "inactive".')
    agent_details: AgentIdentitySummary = Field(description="The agent's name and description.")
    created_at: datetime = Field(description="When the agent was created (UTC).")
    updated_at: datetime = Field(description="When the agent's identity fields were last updated (UTC).")


class EnvironmentSummary(BaseModel):
    """One row of GET /agents/{agent_id}/environments — lets a client show all
    three environments (and when each was last promoted/edited) without
    fetching each one's full config.
    """

    environment: Environment = Field(
        description='Which environment this row describes: "development", "stage", or "production".'
    )
    # False until the environment has ever been populated (a promotion, for stage/production)
    exists: bool = Field(
        description='Whether this environment has ever been populated. Always `true` for "development"; '
        '`false` for "stage"/"production" until the first promotion.'
    )
    updated_at: datetime | None = Field(None, description="When this environment was last updated (UTC), or `null` if it doesn't exist yet.")


class AgentStatusUpdate(BaseModel):
    """Body for PATCH /agents/{agent_id}/status. POST .../activate and
    .../deactivate are shortcuts for the two possible values — all three
    routes go through agents.service.update_status.
    """

    model_config = ConfigDict(json_schema_extra={"example": {"status": "inactive"}})

    status: AgentStatus = Field(description='The new status to set: "active" or "inactive".')
