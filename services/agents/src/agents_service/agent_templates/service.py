from common.errors import NotFoundError

from agents_service.agent_configs import repository as config_repo
from agents_service.agent_details.schema import AgentDetails
from agents_service.agent_templates.data import TEMPLATES
from agents_service.agent_templates.schema import AgentFromTemplateRequest, AgentTemplate, AgentTemplateSummary
from agents_service.agents import service as agent_service
from agents_service.agents.model import Agent
from agents_service.agent_configs.model import AgentConfig
from agents_service.core.deps import AuthContext
from agents_service.faq.schema import FAQSettings
from agents_service.prompt import service as prompt_service
from agents_service.prompt.schema import AgentPrompt


def list_templates() -> list[AgentTemplateSummary]:
    return [
        AgentTemplateSummary(
            key=t.key, name=t.name, category=t.category, description=t.description, direction=t.direction, languages=t.languages
        )
        for t in TEMPLATES.values()
    ]


def get_template(key: str) -> AgentTemplate:
    template = TEMPLATES.get(key)
    if template is None:
        raise NotFoundError("Agent template not found")
    return template


async def create_agent_from_template(
    auth: AuthContext, key: str, request: AgentFromTemplateRequest
) -> tuple[Agent, AgentConfig]:
    template = get_template(key)
    agent, config = await agent_service.create_agent(
        auth,
        AgentDetails(name=request.name or template.name, description=request.description or template.description),
    )

    prompt = AgentPrompt(
        welcome_message=template.welcome_message,
        system_prompt=template.system_prompt,
        ending_message=template.ending_message,
        pre_call_variables=dict(template.pre_call_variables),
    )
    prompt_service.validate_prompt(prompt)
    config.languages = list(template.languages)
    config.prompt = prompt
    config.faq = FAQSettings(enabled=True, pairs=[p.model_copy() for p in template.faq])
    await config_repo.save(config)
    return agent, config
