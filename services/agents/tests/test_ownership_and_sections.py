import pytest
from beanie import PydanticObjectId

from agents_service.agent_configs.model import AgentConfig
from agents_service.prompt.version_model import SystemPromptVersion
from tests.factories import code, data, set_auth

pytestmark = pytest.mark.asyncio


async def test_agent_details_patch_splits_across_identity_and_config(client):
    # name/description live on the `agents` collection (identity);
    # region/timezone/bot_type live on `agent_configs` — a single PATCH to
    # this one tab should still update both transparently. `languages` is
    # deliberately not part of this tab — see test_languages.py.
    set_auth(client.app, "user-1", "org-1")
    create_resp = await client.post("/api/v1/agents", json={"name": "Split Fields"})
    agent_id = data(create_resp)["id"]

    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/agent-details",
        json={"name": "Renamed", "description": "New description", "region": "us"},
    )
    assert code(resp) == 200
    body = data(resp)
    assert body["agent_details"]["name"] == "Renamed"
    assert body["agent_details"]["description"] == "New description"
    assert body["agent_details"]["region"] == "us"
    # Untouched agent_details fields keep their defaults.
    assert body["agent_details"]["timezone"] == "Asia/Kolkata"

    get_resp = await client.get(f"/api/v1/agents/{agent_id}")
    assert data(get_resp)["agent_details"]["name"] == "Renamed"


async def test_agent_in_another_org_is_404_not_403(client):
    set_auth(client.app, "user-a", "org-a")
    create_resp = await client.post("/api/v1/agents", json={"name": "Org A Agent"})
    agent_id = data(create_resp)["id"]

    set_auth(client.app, "user-b", "org-b")
    get_resp = await client.get(f"/api/v1/agents/{agent_id}")
    assert get_resp.status_code == 200
    assert code(get_resp) == 404

    patch_resp = await client.patch(f"/api/v1/agents/{agent_id}/agent-details", json={"name": "Hijacked"})
    assert code(patch_resp) == 404

    delete_resp = await client.delete(f"/api/v1/agents/{agent_id}")
    assert code(delete_resp) == 404


async def test_list_returns_every_org_agent_for_admin(client):
    # Admin visibility is org-wide, not limited to agents the caller
    # personally created — see agents.service.list_agents. Developer-scoped
    # (assigned-only) listing is covered in test_authorization.py.
    set_auth(client.app, "user-a", "org-a")
    await client.post("/api/v1/agents", json={"name": "A1"})

    set_auth(client.app, "user-b", "org-a")
    await client.post("/api/v1/agents", json={"name": "B1"})

    list_resp = await client.get("/api/v1/agents")
    names = {a["agent_details"]["name"] for a in data(list_resp)}
    assert names == {"A1", "B1"}


async def test_list_does_not_include_agent_config(client):
    # GET /agents is identity-only (AgentListItem) — no builder-tab sections,
    # no environment/languages/region/timezone/bot_type, none of which come
    # off the Agent document itself. GET /agents/{id} (AgentOut) still has
    # all of it.
    set_auth(client.app, "user-1", "org-1")
    create_resp = await client.post("/api/v1/agents", json={"name": "Listed"})
    agent_id = data(create_resp)["id"]
    await client.patch(f"/api/v1/agents/{agent_id}/llm", json={"provider_id": "openai", "model_id": "gpt-4o-mini"})

    row = data(await client.get("/api/v1/agents"))[0]
    assert set(row) == {"id", "user_id", "org_id", "status", "agent_details", "created_at", "updated_at"}
    assert set(row["agent_details"]) == {"name", "description"}
    assert row["agent_details"]["name"] == "Listed"

    full = data(await client.get(f"/api/v1/agents/{agent_id}"))
    assert full["llm"]["provider_id"] == "openai"


async def test_patching_one_section_does_not_clobber_others(client):
    set_auth(client.app, "user-1", "org-1")
    create_resp = await client.post("/api/v1/agents", json={"name": "Multi Section"})
    agent_id = data(create_resp)["id"]

    await client.patch(f"/api/v1/agents/{agent_id}/llm", json={"provider_id": "openai", "model_id": "gpt-4o-mini"})
    await client.patch(f"/api/v1/agents/{agent_id}/transcriber", json={"provider_id": "gnani"})

    get_resp = await client.get(f"/api/v1/agents/{agent_id}")
    body = data(get_resp)
    assert body["llm"]["provider_id"] == "openai"
    assert body["llm"]["model_id"] == "gpt-4o-mini"
    # Untouched fields on the same section keep their defaults.
    assert body["llm"]["temperature"] == 0.2
    # A different section's patch didn't touch llm at all.
    assert body["transcriber"]["provider_id"] == "gnani"
    assert body["agent_details"]["name"] == "Multi Section"


async def test_partial_patch_only_changes_supplied_fields(client):
    set_auth(client.app, "user-1", "org-1")
    create_resp = await client.post("/api/v1/agents", json={"name": "Partial Patch"})
    agent_id = data(create_resp)["id"]

    await client.patch(
        f"/api/v1/agents/{agent_id}/transcriber", json={"provider_id": "gnani", "noise_suppression_level": 90}
    )
    resp = await client.patch(f"/api/v1/agents/{agent_id}/transcriber", json={"tier": "accurate"})
    body = data(resp)
    assert body["transcriber"]["provider_id"] == "gnani"
    assert body["transcriber"]["noise_suppression_level"] == 90
    assert body["transcriber"]["tier"] == "accurate"


async def test_unknown_section_has_no_route(client):
    # Each tab owns its own literal PATCH route (see agents/schema.py's
    # SECTIONS table and each section's own router.py), so a bogus section
    # name never reaches the app's business logic — it's a routing 404, not
    # our {status, code, errors} envelope.
    set_auth(client.app, "user-1", "org-1")
    create_resp = await client.post("/api/v1/agents", json={"name": "Bad Section"})
    agent_id = data(create_resp)["id"]

    resp = await client.patch(f"/api/v1/agents/{agent_id}/not-a-real-section", json={})
    assert resp.status_code == 404


async def test_deleted_agent_is_not_returned(client):
    set_auth(client.app, "user-1", "org-1")
    create_resp = await client.post("/api/v1/agents", json={"name": "To Delete"})
    agent_id = data(create_resp)["id"]

    delete_resp = await client.delete(f"/api/v1/agents/{agent_id}")
    assert code(delete_resp) == 200

    get_resp = await client.get(f"/api/v1/agents/{agent_id}")
    assert code(get_resp) == 404

    list_resp = await client.get("/api/v1/agents")
    assert data(list_resp) == []


async def test_deleting_an_agent_removes_all_related_data(client):
    # DELETE is a hard delete, cascading to every environment's AgentConfig
    # and every SystemPromptVersion row — not just the Agent identity
    # document. Verified directly against the collections, not just via the
    # API (a 404 on GET alone wouldn't catch an orphaned AgentConfig/version).
    set_auth(client.app, "user-1", "org-1")
    create_resp = await client.post("/api/v1/agents", json={"name": "Cascade Delete"})
    agent_id = data(create_resp)["id"]

    await client.post(
        f"/api/v1/agents/{agent_id}/prompt/versions", json={"prompt_key": "v1", "system_prompt": "Be helpful."}
    )
    await client.patch(f"/api/v1/agents/{agent_id}/prompt/messages", json={"system_prompt": "v1"})
    await client.post(f"/api/v1/agents/{agent_id}/move-to-stage")  # creates a second AgentConfig (stage)

    oid = PydanticObjectId(agent_id)
    assert await AgentConfig.find(AgentConfig.agent_id == oid).count() == 2  # development + stage
    assert await SystemPromptVersion.find(SystemPromptVersion.agent_id == oid).count() == 1

    delete_resp = await client.delete(f"/api/v1/agents/{agent_id}")
    assert code(delete_resp) == 200

    assert await AgentConfig.find(AgentConfig.agent_id == oid).count() == 0
    assert await SystemPromptVersion.find(SystemPromptVersion.agent_id == oid).count() == 0


async def test_replace_route_no_longer_exists(client):
    set_auth(client.app, "user-1", "org-1")
    create_resp = await client.post("/api/v1/agents", json={"name": "No PUT"})
    agent_id = data(create_resp)["id"]

    resp = await client.put(f"/api/v1/agents/{agent_id}", json={"agent_details": {"name": "Replaced"}})
    # 405, not 404: GET/DELETE still exist on this path, PUT just isn't
    # registered any more — a routing-level rejection, not our envelope.
    assert resp.status_code == 405
