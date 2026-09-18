"""The `agent_configs` collection: the relatively-stable, per-agent config
aggregate — everything about an agent except its identity (see agents/model.py
for the `agents` collection: id, org_id, user_id, name, description, status).

One `AgentConfig` per (`Agent`, `environment`), edited section-by-section via
each tab's own PATCH route (agents.service.update_section, dispatched through
the SECTIONS table in agents/schema.py) — those routes always target
`development`, the one environment a caller edits directly. `stage` and
`production` are read-only snapshots, written only by promotion (see
agents.service.promote_environment / the /move-to-stage and /move-to-prod
routes), never by a section PATCH. `prompt` has no PATCH route of its own
any more (see prompt/router.py — every one of its fields is covered by a
narrower, dedicated route instead), and also owns `pre_call_variables` and
`dynamic_message`, not this document directly — see prompt/schema.py.
`prompt.system_prompt` is plain text, edited and stored directly — the
`system_prompt_versions` collection (see prompt/version_model.py) is only
an optional, independent library of reusable snippets, not a revision
history for this field. `analytics.post_call_trigger` (see
post_call_trigger/schema.py — it replaced `others.post_call_trigger_url`)
similarly gets its own POST/GET/PATCH /agents/{id}/post-call-trigger
routes on top of the generic `analytics` PATCH, not a section of its own.
"""

from datetime import datetime, timezone
from typing import Literal

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

Environment = Literal["development", "stage", "production"]

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
    environment: Environment = "development"

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
        indexes = [IndexModel([("agent_id", 1), ("environment", 1)], unique=True)]
