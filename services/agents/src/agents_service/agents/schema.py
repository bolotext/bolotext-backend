from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from agents_service.actions.schema import ActionsSettings, ActionsSettingsUpdate
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

    id: str
    user_id: str
    org_id: str | None
    status: AgentStatus
    agent_details: AgentDetails
    prompt: AgentPrompt
    flow: AgentFlow
    transcriber: TranscriberSettings
    llm: LLMSettings
    voice_persona: VoicePersonaSection
    analytics: AnalyticsSettings
    others: OthersSettings
    faq: FAQSettings
    deployment: DeploymentSettings
    actions: ActionsSettings
    mcp: MCPSettings
    created_at: datetime
    updated_at: datetime


class AgentReplace(BaseModel):
    """Body for PUT /agents/{agent_id} — a full replace of every section.
    `status` isn't included: publishing goes through the dedicated /publish
    endpoint, not a blind full-document overwrite.
    """

    agent_details: AgentDetails
    prompt: AgentPrompt = AgentPrompt()
    flow: AgentFlow = AgentFlow()
    transcriber: TranscriberSettings = TranscriberSettings()
    llm: LLMSettings = LLMSettings()
    voice_persona: VoicePersonaSection = VoicePersonaSection()
    analytics: AnalyticsSettings = AnalyticsSettings()
    others: OthersSettings = OthersSettings()
    faq: FAQSettings = FAQSettings()
    deployment: DeploymentSettings = DeploymentSettings()
    actions: ActionsSettings = ActionsSettings()
    mcp: MCPSettings = MCPSettings()
