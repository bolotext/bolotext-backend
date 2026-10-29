import pytest

from tests.factories import code, data, error_type, set_auth

pytestmark = pytest.mark.asyncio


async def _make_ready_agent(client, name: str) -> str:
    create_resp = await client.post("/api/v1/agents", json={"name": name})
    agent_id = data(create_resp)["id"]

    await client.patch(
        f"/api/v1/agents/{agent_id}/prompt/messages",
        json={"welcome_message": "Hi.", "system_prompt": "Be helpful.", "ending_message": "Bye."},
    )
    await client.patch(f"/api/v1/agents/{agent_id}/transcriber", json={"provider_id": "gnani"})
    await client.patch(f"/api/v1/agents/{agent_id}/llm", json={"provider_id": "openai", "model_id": "gpt-4o-mini"})
    await client.patch(
        f"/api/v1/agents/{agent_id}/voice-persona",
        json={
            "personas": [
                {
                    "persona_id": "p1",
                    "name": "Neha",
                    "provider_id": "elevenlabs",
                    "voice_id": "voice-1",
                    "is_default": True,
                }
            ]
        },
    )
    return agent_id


async def test_new_agent_defaults_to_development_and_other_environments_start_empty(client):
    set_auth(client.app, "user-1", "org-1")
    create_resp = await client.post("/api/v1/agents", json={"name": "Fresh"})
    agent_id = data(create_resp)["id"]
    assert data(create_resp)["environment"] == "development"

    summaries = data(await client.get(f"/api/v1/agents/{agent_id}/environments"))
    by_env = {row["environment"]: row for row in summaries}
    assert by_env["development"]["exists"] is True
    assert by_env["stage"]["exists"] is False
    assert by_env["production"]["exists"] is False


async def test_move_to_stage_copies_development_config(client):
    set_auth(client.app, "user-1", "org-1")
    agent_id = await _make_ready_agent(client, "Promotable")

    stage_resp = await client.post(f"/api/v1/agents/{agent_id}/move-to-stage")
    assert code(stage_resp) == 200
    staged = data(stage_resp)
    assert staged["environment"] == "stage"
    assert staged["llm"]["provider_id"] == "openai"
    assert staged["prompt"]["system_prompt"] == "Be helpful."

    fetched = data(await client.get(f"/api/v1/agents/{agent_id}/environments/stage"))
    assert fetched["llm"]["provider_id"] == "openai"


async def test_move_to_prod_requires_stage_to_be_complete(client):
    set_auth(client.app, "user-1", "org-1")
    create_resp = await client.post("/api/v1/agents", json={"name": "Incomplete"})
    agent_id = data(create_resp)["id"]

    resp = await client.post(f"/api/v1/agents/{agent_id}/move-to-prod")
    assert code(resp) == 422
    missing = set(resp.json()["errors"]["missing_sections"])
    assert missing == {"prompt", "transcriber", "llm", "voice_persona"}


async def test_move_to_prod_copies_from_stage_not_development(client):
    set_auth(client.app, "user-1", "org-1")
    agent_id = await _make_ready_agent(client, "Pipeline")

    await client.post(f"/api/v1/agents/{agent_id}/move-to-stage")

    # Edit development further after staging — production should still come
    # from stage, not from this newer development state.
    await client.patch(f"/api/v1/agents/{agent_id}/llm", json={"provider_id": "openai", "model_id": "gpt-4o"})

    prod_resp = await client.post(f"/api/v1/agents/{agent_id}/move-to-prod")
    assert code(prod_resp) == 200
    prod = data(prod_resp)
    assert prod["environment"] == "production"
    assert prod["llm"]["model_id"] == "gpt-4o-mini"

    dev = data(await client.get(f"/api/v1/agents/{agent_id}/environments/development"))
    assert dev["llm"]["model_id"] == "gpt-4o"


async def test_move_to_prod_before_move_to_stage_sees_empty_stage(client):
    set_auth(client.app, "user-1", "org-1")
    agent_id = await _make_ready_agent(client, "SkipStage")

    # development is ready, but stage was never populated — production must
    # come from stage, so this should fail the completeness check even
    # though development itself is complete.
    resp = await client.post(f"/api/v1/agents/{agent_id}/move-to-prod")
    assert code(resp) == 422


async def test_get_unknown_environment_is_rejected(client):
    set_auth(client.app, "user-1", "org-1")
    create_resp = await client.post("/api/v1/agents", json={"name": "BadEnv"})
    agent_id = data(create_resp)["id"]

    resp = await client.get(f"/api/v1/agents/{agent_id}/environments/qa")
    assert resp.json()["errors"]["type"] == "VALIDATION_ERROR"


async def test_get_environment_404s_when_not_yet_promoted_into(client):
    # Unlike get_agent (which self-heals a missing "development" config),
    # GET .../environments/{env} never fabricates one — stage/production
    # genuinely don't exist until move-to-stage/move-to-prod has run.
    set_auth(client.app, "user-1", "org-1")
    create_resp = await client.post("/api/v1/agents", json={"name": "NotPromoted"})
    agent_id = data(create_resp)["id"]

    stage_resp = await client.get(f"/api/v1/agents/{agent_id}/environments/stage")
    assert code(stage_resp) == 404
    assert error_type(stage_resp) == "NOT_FOUND"

    prod_resp = await client.get(f"/api/v1/agents/{agent_id}/environments/production")
    assert code(prod_resp) == 404

    # development always exists (created alongside the agent), so it's
    # unaffected.
    dev_resp = await client.get(f"/api/v1/agents/{agent_id}/environments/development")
    assert code(dev_resp) == 200


async def test_environments_are_scoped_to_the_owning_org(client):
    set_auth(client.app, "user-1", "org-1")
    agent_id = await _make_ready_agent(client, "OrgScoped")
    await client.post(f"/api/v1/agents/{agent_id}/move-to-stage")

    set_auth(client.app, "user-2", "org-2")
    resp = await client.get(f"/api/v1/agents/{agent_id}/environments/stage")
    assert resp.json()["errors"]["type"] == "NOT_FOUND"


async def test_config_by_query_params(client):
    set_auth(client.app, "user-1", "org-1")
    agent_id = await _make_ready_agent(client, "Queryable")

    dev = await client.get("/api/v1/agents/config", params={"agent_id": agent_id, "environment": "development"})
    assert code(dev) == 200
    assert data(dev)["environment"] == "development"

    # Not promoted yet -> 404, not an empty config.
    assert code(await client.get("/api/v1/agents/config", params={"agent_id": agent_id, "environment": "stage"})) == 404

    await client.post(f"/api/v1/agents/{agent_id}/move-to-stage")
    resp = await client.get("/api/v1/agents/config", params={"agent_id": agent_id, "environment": "stage"})
    assert code(resp) == 200
    assert data(resp)["environment"] == "stage"
    assert data(resp)["llm"]["provider_id"] == "openai"
    # The old "staging" alias is gone.
    assert code(await client.get("/api/v1/agents/config", params={"agent_id": agent_id, "environment": "staging"})) == 422

    await client.post(f"/api/v1/agents/{agent_id}/move-to-prod")
    prod = await client.get("/api/v1/agents/config", params={"agent_id": agent_id, "environment": "production"})
    assert data(prod)["environment"] == "production"


async def test_config_by_query_params_validation_and_ownership(client):
    set_auth(client.app, "user-1", "org-1")
    agent_id = await _make_ready_agent(client, "Mine")

    assert code(await client.get("/api/v1/agents/config", params={"agent_id": agent_id, "environment": "qa"})) == 422
    assert code(await client.get("/api/v1/agents/config", params={"environment": "development"})) == 422

    set_auth(client.app, "user-2", "org-2")
    other = await client.get("/api/v1/agents/config", params={"agent_id": agent_id, "environment": "development"})
    assert code(other) == 404


async def test_api_token_reads_config_but_only_on_the_config_route(client):
    from agents_service.core import http_client
    from agents_service.core.deps import get_current_auth, get_introspection
    from agents_service.core.http_client import IntrospectResult

    set_auth(client.app, "user-1", "org-1")
    agent_id = await _make_ready_agent(client, "Tokenised")
    await client.post(f"/api/v1/agents/{agent_id}/move-to-stage")

    # Switch to a real introspection result for an API token (no user override).
    client.app.dependency_overrides.pop(get_current_auth, None)
    result = IntrospectResult(active=True, token_type="api_token", scopes=["agent-config:read"], token_id="t1")
    client.app.dependency_overrides[get_introspection] = lambda: result

    ok = await client.get("/api/v1/agents/config", params={"agent_id": agent_id, "environment": "stage"})
    assert code(ok) == 200 and data(ok)["environment"] == "stage"  # no ownership needed
    assert code(await client.get("/api/v1/agents/config", params={"agent_id": agent_id, "environment": "production"})) == 404
    missing = "000000000000000000000000"
    assert code(await client.get("/api/v1/agents/config", params={"agent_id": missing, "environment": "development"})) == 404

    # The token is rejected everywhere else.
    assert code(await client.get(f"/api/v1/agents/{agent_id}")) == 401
    assert code(await client.get("/api/v1/agents")) == 401

    # A token without the scope is forbidden, a revoked/unknown one unauthorized.
    client.app.dependency_overrides[get_introspection] = lambda: IntrospectResult(active=True, token_type="api_token", scopes=[])
    assert code(await client.get("/api/v1/agents/config", params={"agent_id": agent_id, "environment": "staging"})) == 403
    client.app.dependency_overrides[get_introspection] = lambda: IntrospectResult(active=False)
    assert code(await client.get("/api/v1/agents/config", params={"agent_id": agent_id, "environment": "staging"})) == 401
