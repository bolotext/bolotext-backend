"""The `agent_configs` collection: the relatively-stable, per-agent config
aggregate — everything about an agent except its identity (see agents/model.py
for the `agents` collection: id, org_id, user_id, name, description, status).

One `AgentConfig` per `Agent`, edited section-by-section via each tab's own
PATCH route (agents.service.update_section, dispatched through the SECTIONS
table in agents/schema.py). Unlike the rest of this document, `system_prompt`
(inside `prompt`) keeps its own bounded revision history — see
prompt/version_model.py — rather than the whole config being versioned.
"""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

from agents_service.actions.schema import ActionsSettings
from agents_service.analytics.schema import AnalyticsSettings
from agents_service.deployment.schema import DeploymentSettings
from agents_service.faq.schema import FAQSettings
from agents_service.flow.schema import AgentFlow
from agents_service.llm.schema import LLMSettings
from agents_service.mcp.schema import MCPSettings
from agents_service.others.schema import OthersSettings
from agents_service.prompt.schema import AgentPrompt
from agents_service.transcriber.schema import TranscriberSettings
from agents_service.voice_persona.schema import VoicePersonaSection


class AgentConfig(Document):
    agent_id: PydanticObjectId

    # The part of the old "Agent Details" tab that isn't identity (see
    # agents/service.update_agent_details, which splits a single PATCH
    # payload across this document and the Agent identity document).
    languages: list[str] = ["en-IN"]
    region: str = "asia"
    timezone: str = "Asia/Kolkata"
    bot_type: list[str] = ["voice"]

    prompt: AgentPrompt = Field(default_factory=AgentPrompt)
    flow: AgentFlow = Field(default_factory=AgentFlow)
    transcriber: TranscriberSettings = Field(default_factory=TranscriberSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    voice_persona: VoicePersonaSection = Field(default_factory=VoicePersonaSection)
    analytics: AnalyticsSettings = Field(default_factory=AnalyticsSettings)
    others: OthersSettings = Field(default_factory=OthersSettings)
    faq: FAQSettings = Field(default_factory=FAQSettings)
    deployment: DeploymentSettings = Field(default_factory=DeploymentSettings)
    actions: ActionsSettings = Field(default_factory=ActionsSettings)
    mcp: MCPSettings = Field(default_factory=MCPSettings)

    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "agent_configs"
        indexes = [IndexModel("agent_id", unique=True)]
