from beanie import PydanticObjectId
from common.enums import Role
from common.errors import BadRequestError, ForbiddenError, NotFoundError, UnprocessableEntityError
from common.log_utils import setup_logger
from pydantic import ValidationError

from agents_service.agent_assignments import repository as assignment_repo
from agents_service.agent_configs import repository as config_repo
from agents_service.agent_configs.model import AgentConfig, Environment
from agents_service.agent_details.schema import AgentDetails, AgentDetailsUpdate
from agents_service.agents import repository as agent_repo
from agents_service.agents.model import Agent, AgentStatus
from agents_service.call_logs.model import CallLog
from agents_service.agents.schema import SECTIONS, AgentIdentitySummary, AgentListItem, AgentOut, EnvironmentSummary
from agents_service.core.deps import AuthContext, write_environment
from agents_service.dynamic_message.schema import DynamicMessageSettingsUpdate
from agents_service.post_call_trigger.schema import PostCallTriggerSettings, PostCallTriggerSettingsUpdate
from agents_service.prompt import service as prompt_service
from agents_service.prompt.schema import AgentPrompt, LanguageSwitchSettingsUpdate, PromptMessagesUpdate

logger = setup_logger(__name__)

# Fields of AgentDetails that live on the Agent identity document rather than
# AgentConfig — see agents/model.py and agent_configs/model.py's docstrings.
_IDENTITY_FIELDS = ("name", "description")
_DETAILS_CONFIG_FIELDS = ("region", "timezone", "bot_type")

# A promotion always moves one step down this pipeline — dev is the only
# environment edited directly; stage and production are only ever written by
# copying the environment before them. Keyed by the *target* environment.
_PROMOTION_SOURCE: dict[Environment, Environment] = {"stage": "development", "production": "stage"}
ENVIRONMENTS: tuple[Environment, ...] = ("development", "stage", "production")


def to_out(agent: Agent, config: AgentConfig) -> AgentOut:
    return AgentOut(
        id=str(agent.id),
        user_id=agent.user_id,
        org_id=agent.org_id,
        status=agent.status,
        environment=config.environment,
        languages=config.languages,
        agent_details=AgentDetails(
            name=agent.name,
            description=agent.description,
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


def to_list_item(agent: Agent) -> AgentListItem:
    return AgentListItem(
        id=str(agent.id),
        user_id=agent.user_id,
        org_id=agent.org_id,
        status=agent.status,
        agent_details=AgentIdentitySummary(name=agent.name, description=agent.description),
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


async def _authorize_agent_access(agent: Agent, auth: AuthContext, *, write: bool) -> None:
    """The single place every Agent API's permission check funnels through
    (via get_owned_agent/get_agent_with_config below, which every router in
    this service goes through). Admin has full access to every agent in
    its org; QA is view-only across the whole org (write=True is always
    rejected); Developer is further restricted to agents explicitly
    assigned to them (see agent_assignments) on top of the org check.
    Super admin bypasses all of it, including the org check.
    """
    if auth.is_super_admin:
        return
    if agent.org_id != auth.organization_id:
        # 404, not 403: an agent in another org should look like it doesn't
        # exist rather than confirming its existence to the wrong caller.
        raise NotFoundError("Agent not found")
    if auth.role == Role.QA:
        if write:
            raise ForbiddenError("QA role has view-only access")
        return
    if auth.role == Role.DEVELOPER:
        if not await assignment_repo.is_assigned(agent.id, auth.user_id):
            # Same 404-not-403 reasoning as the org check above: an agent
            # that exists but isn't assigned to this developer shouldn't be
            # distinguishable from one that doesn't exist at all.
            raise NotFoundError("Agent not found")
        return
    # ADMIN: full access to every agent in its own org.


async def get_owned_agent(agent_id: PydanticObjectId, auth: AuthContext, *, write: bool = True) -> Agent:
    agent = await agent_repo.get_by_id(agent_id)
    if agent is None:
        raise NotFoundError("Agent not found")
    await _authorize_agent_access(agent, auth, write=write)
    return agent


async def _get_config(agent_id: PydanticObjectId, environment: Environment = "development") -> AgentConfig:
    config = await config_repo.get_by_agent_id(agent_id, environment)
    if config is None:
        # For "development" this should only happen if create_agent's second
        # insert failed after the first committed. For "stage"/"production"
        # it's the normal first-time case: they don't exist until promoted
        # into, so self-heal an empty one rather than 404 on a fresh agent.
        config = await config_repo.create_config(agent_id, environment)
    return config


async def get_agent_with_config(
    agent_id: PydanticObjectId,
    auth: AuthContext,
    environment: Environment | None = None,
    *,
    write: bool = True,
) -> tuple[Agent, AgentConfig]:
    # Unspecified: writes follow the request's `?env=` (development
    # or stage — see core.deps.bind_write_environment); reads stay on development.
    if environment is None:
        environment = write_environment.get() if write else "development"
    agent = await get_owned_agent(agent_id, auth, write=write)
    config = await _get_config(agent.id, environment)
    return agent, config


async def _auto_assign_if_developer(agent: Agent, auth: AuthContext) -> None:
    """A Developer can only access agents explicitly assigned to them (see
    _authorize_agent_access) — so an agent they just created or cloned must
    be assigned to them immediately, or they'd have no way to reach it
    afterwards.
    """
    if auth.role == Role.DEVELOPER and not auth.is_super_admin:
        await assignment_repo.create(agent.id, auth.user_id, auth.organization_id, assigned_by=auth.user_id)


async def create_agent(auth: AuthContext, details: AgentDetails) -> tuple[Agent, AgentConfig]:
    if auth.role == Role.QA and not auth.is_super_admin:
        raise ForbiddenError("QA role cannot create agents")

    agent = await agent_repo.create_agent(
        user_id=auth.user_id, org_id=auth.organization_id, name=details.name, description=details.description
    )
    config = await config_repo.create_config(agent.id)
    # config.languages keeps AgentConfig's own default (["en-IN"]) — an agent
    # is always created English-only; see update_languages for how it's
    # configured afterwards.
    config.region = details.region
    config.timezone = details.timezone
    config.bot_type = details.bot_type
    await config_repo.save(config)
    await _auto_assign_if_developer(agent, auth)
    logger.info(f"agent created: agent_id=%s user_id=%s", agent.id, auth.user_id)
    return agent, config


async def list_agents(auth: AuthContext, skip: int, limit: int, status: AgentStatus | None) -> list[Agent]:
    """GET /agents — identity only (see to_list_item/AgentListItem), so this
    never touches AgentConfig: no per-agent config read/self-heal here.
    Visibility mirrors _authorize_agent_access: Admin/QA/super-admin see
    every agent in the org, Developer sees only agents assigned to them.
    """
    if auth.role == Role.DEVELOPER and not auth.is_super_admin:
        agent_ids = await assignment_repo.list_agent_ids_for_user(auth.user_id, auth.organization_id)
        return await agent_repo.list_by_ids(agent_ids, skip=skip, limit=limit, status=status)
    if auth.is_super_admin and auth.organization_id is None:
        # No org context to scope by — unchanged pre-existing behavior of
        # falling back to the caller's own agents rather than every agent
        # across every org.
        return await agent_repo.list_agents(user_id=auth.user_id, skip=skip, limit=limit, status=status)
    return await agent_repo.list_by_org(auth.organization_id, skip=skip, limit=limit, status=status)


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

    logger.info(f"agent details updated: agent_id={agent.id} user_id={auth.user_id}")
    return agent, config


async def update_languages(agent_id: PydanticObjectId, auth: AuthContext, languages: list[str]) -> tuple[Agent, AgentConfig]:
    """PUT /agents/{id}/languages — the only place AgentConfig.languages ever
    changes (create_agent leaves it at AgentConfig's own default; see its
    comment).
    """
    if not languages:
        raise UnprocessableEntityError("languages must contain at least one language")

    agent, config = await get_agent_with_config(agent_id, auth)
    config.languages = list(languages)
    await config_repo.save(config)
    logger.info(f"agent languages updated: agent_id={agent.id} user_id={auth.user_id} languages={languages}")
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
        await _save_prompt(config, merged)
    else:
        setattr(config, spec.attr, merged)
        await config_repo.save(config)
    logger.info(f"agent section updated: agent_id={agent.id} user_id={auth.user_id} section={section}")
    return agent, config


def _merge_prompt(config: AgentConfig, provided: dict) -> AgentPrompt:
    try:
        return AgentPrompt.model_validate({**config.prompt.model_dump(), **provided})
    except ValidationError as exc:
        raise UnprocessableEntityError("Invalid prompt payload", {"fields": exc.errors()}) from exc


async def _save_prompt(config: AgentConfig, merged: AgentPrompt) -> None:
    """Every save that touches config.prompt — regardless of which endpoint
    or which subset of its fields — re-validates the whole section: welcome/
    ending text against pre_call_variables, and the custom-mode language-
    switch requirement. Keeps /prompt/messages, /prompt/language-switch,
    /pre-call-variables, and /dynamic-message all honoring the same
    invariants, not just the ones that happen to touch the fields a given
    check cares about. `system_prompt` is plain text now (see AgentPrompt's
    docstring) — nothing to validate it against here.
    """
    prompt_service.validate_prompt(merged)
    prompt_service.validate_language_switch(merged)

    config.prompt = merged
    await config_repo.save(config)


async def update_prompt_messages(agent_id: PydanticObjectId, auth: AuthContext, payload: dict) -> tuple[Agent, AgentConfig]:
    """PATCH /agents/{id}/prompt/messages — the only way to change
    welcome_message/system_prompt/ending_message (see agents_service.prompt.
    schema.PromptMessages), without touching the language-switch fields,
    pre_call_variables, or dynamic_message.
    """
    try:
        update = PromptMessagesUpdate.model_validate(payload)
    except ValidationError as exc:
        raise UnprocessableEntityError("Invalid payload for prompt messages", {"fields": exc.errors()}) from exc

    agent, config = await get_agent_with_config(agent_id, auth)
    merged = _merge_prompt(config, update.model_dump(exclude_unset=True))
    await _save_prompt(config, merged)
    logger.info(f"agent prompt messages updated: agent_id={agent.id} user_id={auth.user_id}")
    return agent, config


async def update_language_switch_settings(
    agent_id: PydanticObjectId, auth: AuthContext, payload: dict
) -> tuple[Agent, AgentConfig]:
    """PATCH /agents/{id}/prompt/language-switch — the only way to change
    (see agents_service.prompt.schema.LanguageSwitchSettings):
    language_switch_mode/language_switch_prompt/
    min_words_for_lang_switch only.
    """
    try:
        update = LanguageSwitchSettingsUpdate.model_validate(payload)
    except ValidationError as exc:
        raise UnprocessableEntityError("Invalid payload for language switch settings", {"fields": exc.errors()}) from exc

    agent, config = await get_agent_with_config(agent_id, auth)
    merged = _merge_prompt(config, update.model_dump(exclude_unset=True))
    await _save_prompt(config, merged)
    logger.info(f"agent language switch settings updated: agent_id={agent.id} user_id={auth.user_id}")
    return agent, config


async def update_pre_call_variables(
    agent_id: PydanticObjectId, auth: AuthContext, pre_call_variables: dict[str, str], pre_call_variables_enabled: bool
) -> tuple[Agent, AgentConfig]:
    """PUT /agents/{id}/pre-call-variables — the only place
    AgentPrompt.pre_call_variables/pre_call_variables_enabled ever change
    (they moved inside `prompt` from bare AgentConfig fields — pre_call_
    variables is also what welcome_message/ending_message {{var}}
    references are validated against, so this goes through _save_prompt
    like every other prompt-touching save, not a bare config_repo.save).
    Unlike languages, an empty mapping is a perfectly normal state (an
    agent with no {{var}} placeholders to declare), so there's no
    non-empty requirement here.
    """
    agent, config = await get_agent_with_config(agent_id, auth)
    merged = _merge_prompt(
        config, {"pre_call_variables": dict(pre_call_variables), "pre_call_variables_enabled": pre_call_variables_enabled}
    )
    await _save_prompt(config, merged)
    logger.info(f"agent pre-call variables updated: agent_id={agent.id} user_id={auth.user_id}")
    return agent, config


async def update_dynamic_message(agent_id: PydanticObjectId, auth: AuthContext, payload: dict) -> tuple[Agent, AgentConfig]:
    """PATCH /agents/{id}/dynamic-message — a partial update of
    AgentPrompt.dynamic_message, merged the same way update_section merges
    any other section (only this one lives inside `prompt`, not directly on
    AgentConfig, so it can't just go through that generic dispatch).
    """
    try:
        update = DynamicMessageSettingsUpdate.model_validate(payload)
    except ValidationError as exc:
        raise UnprocessableEntityError("Invalid payload for dynamic message configuration", {"fields": exc.errors()}) from exc

    agent, config = await get_agent_with_config(agent_id, auth)
    dynamic_message_data = {**config.prompt.dynamic_message.model_dump(), **update.model_dump(exclude_unset=True)}
    merged = _merge_prompt(config, {"dynamic_message": dynamic_message_data})
    await _save_prompt(config, merged)
    logger.info(f"agent dynamic message configuration updated: agent_id={agent.id} user_id={auth.user_id}")
    return agent, config


async def update_post_call_trigger(agent_id: PydanticObjectId, auth: AuthContext, payload: dict) -> tuple[Agent, AgentConfig]:
    """PATCH /agents/{id}/post-call-trigger — a partial update of
    AgentConfig.analytics.post_call_trigger. Nested inside `analytics`, not
    a section of its own (see AnalyticsSettings.post_call_trigger's
    docstring), so it can't just go through the generic update_section
    dispatch the way a top-level section's PATCH route does.
    """
    try:
        update = PostCallTriggerSettingsUpdate.model_validate(payload)
    except ValidationError as exc:
        raise UnprocessableEntityError(
            "Invalid payload for post-call trigger configuration", {"fields": exc.errors()}
        ) from exc

    agent, config = await get_agent_with_config(agent_id, auth)
    current = config.analytics.post_call_trigger
    merged_data = {**current.model_dump(), **update.model_dump(exclude_unset=True)}
    try:
        merged = PostCallTriggerSettings.model_validate(merged_data)
    except ValidationError as exc:
        raise UnprocessableEntityError(
            "Invalid payload for post-call trigger configuration", {"fields": exc.errors()}
        ) from exc

    config.analytics.post_call_trigger = merged
    await config_repo.save(config)
    logger.info(f"agent post-call trigger configuration updated: agent_id={agent.id} user_id={auth.user_id}")
    return agent, config


async def delete_agent(agent_id: PydanticObjectId, auth: AuthContext) -> tuple[Agent, AgentConfig]:
    """DELETE /agents/{id} — a hard delete, and a cascading one: every
    environment's AgentConfig (development/stage/production) and every
    SystemPromptVersion row for this agent are removed too, before the Agent
    identity document itself. There is no soft-delete/recovery. The returned
    (agent, config) pair reflects what was just deleted, for the response
    body — both are already-fetched Python objects, not further reads.
    """
    agent, config = await get_agent_with_config(agent_id, auth)
    await config_repo.delete_all_by_agent_id(agent.id)
    await prompt_service.delete_all_system_prompt_versions(agent.id)
    await assignment_repo.delete_all_by_agent_id(agent.id)
    await CallLog.find(CallLog.agent_id == str(agent.id)).delete()  # transcripts go with the agent
    await agent_repo.delete(agent)
    logger.info(f"agent deleted: agent_id={agent.id} user_id={auth.user_id}")
    return agent, config


def _missing_sections(config: AgentConfig) -> list[str]:
    """Used only by promote_environment's production-readiness gate below —
    there's no separate "publish" step any more (an agent is usable as soon
    as it's created; see Agent.status's docstring), so this no longer gates
    anything on the Agent identity document itself.
    """
    missing = []
    if not (config.prompt.welcome_message and config.prompt.system_prompt and config.prompt.ending_message):
        missing.append("prompt")
    if not config.transcriber.provider_id:
        missing.append("transcriber")
    if not (config.llm.provider_id and config.llm.model_id):
        missing.append("llm")
    if not (config.voice_persona.provider_id and config.voice_persona.voice_id):
        missing.append("voice_persona")
    return missing


async def update_status(agent_id: PydanticObjectId, auth: AuthContext, status: AgentStatus) -> tuple[Agent, AgentConfig]:
    """PATCH /agents/{id}/status — the only place Agent.status changes.
    POST .../activate and .../deactivate (below) are just this with the
    value fixed, for callers that don't want to construct a body.
    """
    agent, config = await get_agent_with_config(agent_id, auth)
    agent.status = status
    await agent_repo.save(agent)
    logger.info(f"agent status updated: agent_id={agent.id} user_id={auth.user_id} status={status}")
    return agent, config


async def activate_agent(agent_id: PydanticObjectId, auth: AuthContext) -> tuple[Agent, AgentConfig]:
    return await update_status(agent_id, auth, "active")


async def deactivate_agent(agent_id: PydanticObjectId, auth: AuthContext) -> tuple[Agent, AgentConfig]:
    return await update_status(agent_id, auth, "inactive")


async def clone_agent(agent_id: PydanticObjectId, auth: AuthContext) -> tuple[Agent, AgentConfig]:
    if auth.role == Role.QA and not auth.is_super_admin:
        raise ForbiddenError("QA role cannot clone agents")

    # write=False: cloning only reads the source agent, it never mutates it.
    source_agent, source_config = await get_agent_with_config(agent_id, auth, write=False)

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
    await _auto_assign_if_developer(clone_agent_doc, auth)

    logger.info(
        f"agent cloned: source_agent_id={source_agent.id} new_agent_id={clone_agent_doc.id} user_id={auth.user_id}"
    )
    return clone_agent_doc, clone_config


async def get_agent_environment(
    agent_id: PydanticObjectId, auth: AuthContext, environment: Environment
) -> tuple[Agent, AgentConfig]:
    """GET /agents/{agent_id}/environments/{environment} — a read-only view of
    one environment's config. Unlike get_agent_with_config (used everywhere
    else, including plain GET /agents/{id}), this does NOT self-heal a
    missing config into existence: `stage`/`production` genuinely don't
    exist until the agent has been promoted into them at least once (see
    list_environment_summaries's `exists` flag), and this route 404s rather
    than silently fabricating an empty one.
    """
    agent = await get_owned_agent(agent_id, auth, write=False)
    config = await config_repo.get_by_agent_id(agent.id, environment)
    if config is None:
        raise NotFoundError(f"Agent has no '{environment}' config yet")
    return agent, config


async def get_agent_environment_for_service(agent_id: PydanticObjectId, environment: Environment) -> tuple[Agent, AgentConfig]:
    """Like get_agent_environment but for an API token (no user, so no ownership
    check — the token's `agent-config:read` scope is the authorization). Never
    self-heals: an unpromoted environment 404s.
    """
    agent = await agent_repo.get_by_id(agent_id)
    if agent is None:
        raise NotFoundError("Agent not found")
    config = await config_repo.get_by_agent_id(agent.id, environment)
    if config is None:
        raise NotFoundError(f"Agent has no '{environment}' config yet")
    return agent, config


async def list_environment_summaries(agent_id: PydanticObjectId, auth: AuthContext) -> list[EnvironmentSummary]:
    agent = await get_owned_agent(agent_id, auth, write=False)
    configs_by_env = {config.environment: config for config in await config_repo.list_by_agent_id(agent.id)}
    return [
        EnvironmentSummary(
            environment=environment,
            exists=environment in configs_by_env,
            updated_at=configs_by_env[environment].updated_at if environment in configs_by_env else None,
        )
        for environment in ENVIRONMENTS
    ]


async def promote_environment(
    agent_id: PydanticObjectId, auth: AuthContext, target: Environment
) -> tuple[Agent, AgentConfig]:
    """Copies every section (plus languages/region/timezone/bot_type) from
    the environment immediately before `target` in the pipeline — never
    skipping a stage, so `production` always reflects what was last verified
    in `stage`, not whatever `development` currently looks like. `target`
    must be "stage" or "production" (`development` has no source to promote
    from — it's edited directly, via the section PATCH routes).
    """
    source_env = _PROMOTION_SOURCE[target]
    agent, source_config = await get_agent_with_config(agent_id, auth, source_env)

    if target == "production":
        # Production shouldn't ever serve an agent that's missing required
        # sections — see _missing_sections.
        missing = _missing_sections(source_config)
        if missing:
            raise UnprocessableEntityError(
                "Agent configuration is incomplete and cannot be promoted to production",
                {"missing_sections": missing},
            )

    target_config = await _get_config(agent.id, target)
    target_config.languages = list(source_config.languages)
    target_config.region = source_config.region
    target_config.timezone = source_config.timezone
    target_config.bot_type = list(source_config.bot_type)
    for spec in SECTIONS.values():
        setattr(target_config, spec.attr, getattr(source_config, spec.attr).model_copy(deep=True))
    await config_repo.save(target_config)

    logger.info(
        f"agent environment promoted: agent_id={agent.id} {source_env} -> {target} user_id={auth.user_id}"
    )
    return agent, target_config


async def move_to_stage(agent_id: PydanticObjectId, auth: AuthContext) -> tuple[Agent, AgentConfig]:
    return await promote_environment(agent_id, auth, "stage")


async def move_to_prod(agent_id: PydanticObjectId, auth: AuthContext) -> tuple[Agent, AgentConfig]:
    return await promote_environment(agent_id, auth, "production")


async def render_test(agent_id: PydanticObjectId, auth: AuthContext, sample_values: dict[str, str]) -> dict:
    _, config = await get_agent_with_config(agent_id, auth, write=False)
    return prompt_service.render_test(config.prompt, sample_values)


async def preview_language_switch_prompt(agent_id: PydanticObjectId, auth: AuthContext) -> tuple[str, list[str], str | None]:
    _, config = await get_agent_with_config(agent_id, auth, write=False)
    rendered = prompt_service.resolve_language_switch_prompt(config.prompt, config.languages)
    return config.prompt.language_switch_mode, config.languages, rendered


# --- agent assignments (Developer access grants; see agent_assignments) -----
# Admin-only, regardless of whether the caller happens to already have write
# access to the agent itself — managing who else can reach an agent is an
# org-management action, not one of the generic per-agent operations.


def _require_admin(auth: AuthContext) -> None:
    if not auth.is_super_admin and auth.role != Role.ADMIN:
        raise ForbiddenError("Only an Admin can manage agent assignments")


async def assign_agent(agent_id: PydanticObjectId, auth: AuthContext, target_user_id: str) -> list[str]:
    agent = await get_owned_agent(agent_id, auth, write=True)
    _require_admin(auth)
    if not await assignment_repo.is_assigned(agent.id, target_user_id):
        await assignment_repo.create(agent.id, target_user_id, agent.org_id, assigned_by=auth.user_id)
    logger.info(f"agent assigned: agent_id={agent.id} user_id={target_user_id} assigned_by={auth.user_id}")
    return await list_agent_assignees(agent_id, auth)


async def unassign_agent(agent_id: PydanticObjectId, auth: AuthContext, target_user_id: str) -> list[str]:
    agent = await get_owned_agent(agent_id, auth, write=True)
    _require_admin(auth)
    assignment = await assignment_repo.get(agent.id, target_user_id)
    if assignment is None:
        raise NotFoundError("Assignment not found")
    await assignment_repo.delete(assignment)
    logger.info(f"agent unassigned: agent_id={agent.id} user_id={target_user_id} by={auth.user_id}")
    return await list_agent_assignees(agent_id, auth)


async def list_agent_assignees(agent_id: PydanticObjectId, auth: AuthContext) -> list[str]:
    agent = await get_owned_agent(agent_id, auth, write=False)
    _require_admin(auth)
    assignments = await assignment_repo.list_for_agent(agent.id)
    return [a.user_id for a in assignments]
