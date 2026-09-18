from beanie import PydanticObjectId
from common.errors import BadRequestError, NotFoundError, UnprocessableEntityError
from common.log_utils import setup_logger
from pydantic import ValidationError

from agents_service.agent_configs import repository as config_repo
from agents_service.agent_configs.model import AgentConfig
from agents_service.agent_details.schema import AgentDetails, AgentDetailsUpdate
from agents_service.agents import repository as agent_repo
from agents_service.agents.model import Agent, AgentStatus
from agents_service.agents.schema import SECTIONS, AgentOut, AgentReplace
from agents_service.core.deps import AuthContext
from agents_service.prompt import service as prompt_service

logger = setup_logger(__name__)

# Fields of AgentDetails that live on the Agent identity document rather than
# AgentConfig — see agents/model.py and agent_configs/model.py's docstrings.
_IDENTITY_FIELDS = ("name", "description")
_DETAILS_CONFIG_FIELDS = ("languages", "region", "timezone", "bot_type")


def to_out(agent: Agent, config: AgentConfig) -> AgentOut:
    return AgentOut(
        id=str(agent.id),
        user_id=agent.user_id,
        org_id=agent.org_id,
        status=agent.status,
        agent_details=AgentDetails(
            name=agent.name,
            description=agent.description,
            languages=config.languages,
            region=config.region,
            timezone=config.timezone,
            bot_type=config.bot_type,
        ),
        prompt=config.prompt,
        flow=config.flow,
        transcriber=config.transcriber,
        llm=config.llm,
        voice_persona=config.voice_persona,
        analytics=config.analytics,
        others=config.others,
        faq=config.faq,
        deployment=config.deployment,
        actions=config.actions,
        mcp=config.mcp,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


def _agent_belongs_to_caller(agent: Agent, auth: AuthContext) -> bool:
    return auth.is_super_admin or agent.org_id == auth.organization_id


async def get_owned_agent(agent_id: PydanticObjectId, auth: AuthContext) -> Agent:
    agent = await agent_repo.get_by_id(agent_id)
    if agent is None or not _agent_belongs_to_caller(agent, auth):
        # 404, not 403: an agent in another org should look like it doesn't
        # exist rather than confirming its existence to the wrong caller.
        raise NotFoundError("Agent not found")
    return agent


async def _get_config(agent_id: PydanticObjectId) -> AgentConfig:
    config = await config_repo.get_by_agent_id(agent_id)
    if config is None:
        # Should only happen if create_agent's second insert failed after the
        # first committed; self-heal rather than leave the agent unusable.
        config = await config_repo.create_config(agent_id)
    return config


async def get_agent_with_config(agent_id: PydanticObjectId, auth: AuthContext) -> tuple[Agent, AgentConfig]:
    agent = await get_owned_agent(agent_id, auth)
    config = await _get_config(agent.id)
    return agent, config


async def create_agent(auth: AuthContext, details: AgentDetails) -> tuple[Agent, AgentConfig]:
    agent = await agent_repo.create_agent(
        user_id=auth.user_id, org_id=auth.organization_id, name=details.name, description=details.description
    )
    config = await config_repo.create_config(agent.id)
    config.languages = details.languages
    config.region = details.region
    config.timezone = details.timezone
    config.bot_type = details.bot_type
    await config_repo.save(config)
    logger.info("agent created: agent_id=%s user_id=%s", agent.id, auth.user_id)
    return agent, config


async def list_agents(
    auth: AuthContext, skip: int, limit: int, status: AgentStatus | None
) -> list[tuple[Agent, AgentConfig]]:
    agents = await agent_repo.list_agents(user_id=auth.user_id, skip=skip, limit=limit, status=status)
    return [(agent, await _get_config(agent.id)) for agent in agents]


async def update_agent_details(agent_id: PydanticObjectId, auth: AuthContext, payload: dict) -> tuple[Agent, AgentConfig]:
    try:
        update = AgentDetailsUpdate.model_validate(payload)
    except ValidationError as exc:
        raise UnprocessableEntityError("Invalid payload for section 'agent-details'", {"fields": exc.errors()}) from exc

    agent, config = await get_agent_with_config(agent_id, auth)
    provided = update.model_dump(exclude_unset=True)

    identity_changed = False
    for field in _IDENTITY_FIELDS:
        if field in provided:
            setattr(agent, field, provided[field])
            identity_changed = True

    config_changed = False
    for field in _DETAILS_CONFIG_FIELDS:
        if field in provided:
            setattr(config, field, provided[field])
            config_changed = True

    if identity_changed:
        await agent_repo.save(agent)
    if config_changed:
        await config_repo.save(config)

    logger.info("agent details updated: agent_id=%s user_id=%s", agent.id, auth.user_id)
    return agent, config


async def update_section(agent_id: PydanticObjectId, auth: AuthContext, section: str, payload: dict) -> tuple[Agent, AgentConfig]:
    spec = SECTIONS.get(section)
    if spec is None:
        raise BadRequestError(f"Unknown agent section '{section}'", {"valid_sections": sorted(SECTIONS)})

    agent, config = await get_agent_with_config(agent_id, auth)

    try:
        update = spec.update_model.model_validate(payload)
        current = getattr(config, spec.attr)
        # exclude_unset (not exclude_none): a field the client omitted stays
        # untouched, but one sent explicitly as null clears it — the partial
        # model's own "not provided" default is also None, so this is the
        # only way to tell the two apart.
        merged_data = {**current.model_dump(), **update.model_dump(exclude_unset=True)}
        merged = spec.full_model.model_validate(merged_data)
    except ValidationError as exc:
        raise UnprocessableEntityError(
            f"Invalid payload for section '{section}'", {"fields": exc.errors()}
        ) from exc

    if section == "prompt":
        prompt_service.validate_prompt(merged)
        # Raises (blocking this whole save) if the agent is already at the
        # cap and system_prompt is part of what changed — see
        # prompt.service.record_system_prompt_version_if_changed.
        await prompt_service.record_system_prompt_version_if_changed(
            agent.id, current.system_prompt, merged.system_prompt, auth.user_id
        )

    setattr(config, spec.attr, merged)
    await config_repo.save(config)
    logger.info("agent section updated: agent_id=%s user_id=%s section=%s", agent.id, auth.user_id, section)
    return agent, config


async def replace_agent(agent_id: PydanticObjectId, auth: AuthContext, payload: AgentReplace) -> tuple[Agent, AgentConfig]:
    agent, config = await get_agent_with_config(agent_id, auth)
    prompt_service.validate_prompt(payload.prompt)
    await prompt_service.record_system_prompt_version_if_changed(
        agent.id, config.prompt.system_prompt, payload.prompt.system_prompt, auth.user_id
    )

    agent.name = payload.agent_details.name
    agent.description = payload.agent_details.description
    await agent_repo.save(agent)

    config.languages = payload.agent_details.languages
    config.region = payload.agent_details.region
    config.timezone = payload.agent_details.timezone
    config.bot_type = payload.agent_details.bot_type
    for spec in SECTIONS.values():
        setattr(config, spec.attr, getattr(payload, spec.attr))
    await config_repo.save(config)

    logger.info("agent replaced: agent_id=%s user_id=%s", agent.id, auth.user_id)
    return agent, config


async def soft_delete_agent(agent_id: PydanticObjectId, auth: AuthContext) -> tuple[Agent, AgentConfig]:
    agent, config = await get_agent_with_config(agent_id, auth)
    await agent_repo.soft_delete(agent)
    logger.info("agent soft-deleted: agent_id=%s user_id=%s", agent.id, auth.user_id)
    return agent, config


def _missing_sections(config: AgentConfig) -> list[str]:
    missing = []
    if not (config.prompt.welcome_message and config.prompt.system_prompt and config.prompt.ending_message):
        missing.append("prompt")
    if not config.transcriber.provider_id:
        missing.append("transcriber")
    if not (config.llm.provider_id and config.llm.model_id):
        missing.append("llm")
    if not config.voice_persona.personas:
        missing.append("voice_persona")
    return missing


async def publish_agent(agent_id: PydanticObjectId, auth: AuthContext) -> tuple[Agent, AgentConfig]:
    agent, config = await get_agent_with_config(agent_id, auth)
    missing = _missing_sections(config)
    if missing:
        raise UnprocessableEntityError(
            "Agent configuration is incomplete and cannot be published", {"missing_sections": missing}
        )

    agent.status = "published"
    await agent_repo.save(agent)
    logger.info("agent published: agent_id=%s user_id=%s", agent.id, auth.user_id)
    return agent, config


async def clone_agent(agent_id: PydanticObjectId, auth: AuthContext) -> tuple[Agent, AgentConfig]:
    source_agent, source_config = await get_agent_with_config(agent_id, auth)

    clone_agent_doc = await agent_repo.create_agent(
        user_id=auth.user_id,
        org_id=source_agent.org_id,
        name=f"{source_agent.name} (Copy)",
        description=source_agent.description,
    )
    clone_config = await config_repo.create_config(clone_agent_doc.id)
    clone_config.languages = list(source_config.languages)
    clone_config.region = source_config.region
    clone_config.timezone = source_config.timezone
    clone_config.bot_type = list(source_config.bot_type)
    for spec in SECTIONS.values():
        setattr(clone_config, spec.attr, getattr(source_config, spec.attr).model_copy(deep=True))
    await config_repo.save(clone_config)

    logger.info(
        "agent cloned: source_agent_id=%s new_agent_id=%s user_id=%s", source_agent.id, clone_agent_doc.id, auth.user_id
    )
    return clone_agent_doc, clone_config


async def render_test(agent_id: PydanticObjectId, auth: AuthContext, sample_values: dict[str, str]) -> dict:
    _, config = await get_agent_with_config(agent_id, auth)
    return prompt_service.render_test(config.prompt, sample_values)
