"""Role/assignment-based authorization — see agents.service._authorize_agent_access.

Admin: full access to every agent in its org.
QA: view-only across the whole org (every mutating route 403s).
Developer: 404 on any agent not explicitly assigned to them (via
agent_assignments); a self-created or self-cloned agent is auto-assigned.
"""

import pytest
from common.enums import Role

from tests.factories import code, data, set_auth

pytestmark = pytest.mark.asyncio


async def _create_agent(client, name: str = "Agent") -> str:
    resp = await client.post("/api/v1/agents", json={"name": name})
    return data(resp)["id"]


# --- QA: view-only ------------------------------------------------------


async def test_qa_cannot_create_agent(client):
    set_auth(client.app, "qa-1", "org-1", role=Role.QA)
    resp = await client.post("/api/v1/agents", json={"name": "Nope"})
    assert code(resp) == 403


async def test_qa_can_read_but_not_write_an_existing_agent(client):
    set_auth(client.app, "admin-1", "org-1", role=Role.ADMIN)
    agent_id = await _create_agent(client, "QA Target")

    set_auth(client.app, "qa-1", "org-1", role=Role.QA)

    get_resp = await client.get(f"/api/v1/agents/{agent_id}")
    assert code(get_resp) == 200

    list_resp = await client.get("/api/v1/agents")
    assert code(list_resp) == 200
    assert any(a["id"] == agent_id for a in data(list_resp))

    envs_resp = await client.get(f"/api/v1/agents/{agent_id}/environments")
    assert code(envs_resp) == 200

    patch_resp = await client.patch(f"/api/v1/agents/{agent_id}/agent-details", json={"name": "Hijacked"})
    assert code(patch_resp) == 403

    section_resp = await client.patch(f"/api/v1/agents/{agent_id}/llm", json={"provider_id": "openai"})
    assert code(section_resp) == 403

    prompt_resp = await client.patch(f"/api/v1/agents/{agent_id}/prompt/messages", json={"system_prompt": "x"})
    assert code(prompt_resp) == 403

    delete_resp = await client.delete(f"/api/v1/agents/{agent_id}")
    assert code(delete_resp) == 403

    clone_resp = await client.post(f"/api/v1/agents/{agent_id}/clone")
    assert code(clone_resp) == 403

    activate_resp = await client.post(f"/api/v1/agents/{agent_id}/activate")
    assert code(activate_resp) == 403

    promote_resp = await client.post(f"/api/v1/agents/{agent_id}/move-to-stage")
    assert code(promote_resp) == 403


async def test_qa_sees_every_agent_in_the_org_not_just_its_own(client):
    set_auth(client.app, "admin-1", "org-1", role=Role.ADMIN)
    await _create_agent(client, "Admin's Agent")

    set_auth(client.app, "qa-1", "org-1", role=Role.QA)
    list_resp = await client.get("/api/v1/agents")
    names = {a["agent_details"]["name"] for a in data(list_resp)}
    assert "Admin's Agent" in names


# --- Developer: assignment-scoped ---------------------------------------


async def test_developer_can_access_a_self_created_agent(client):
    set_auth(client.app, "dev-1", "org-1", role=Role.DEVELOPER)
    agent_id = await _create_agent(client, "Dev Agent")

    get_resp = await client.get(f"/api/v1/agents/{agent_id}")
    assert code(get_resp) == 200

    patch_resp = await client.patch(f"/api/v1/agents/{agent_id}/agent-details", json={"name": "Renamed"})
    assert code(patch_resp) == 200

    list_resp = await client.get("/api/v1/agents")
    ids = {a["id"] for a in data(list_resp)}
    assert agent_id in ids


async def test_developer_gets_404_on_an_unassigned_teammates_agent(client):
    set_auth(client.app, "dev-1", "org-1", role=Role.DEVELOPER)
    agent_id = await _create_agent(client, "Dev1 Agent")

    set_auth(client.app, "dev-2", "org-1", role=Role.DEVELOPER)
    get_resp = await client.get(f"/api/v1/agents/{agent_id}")
    assert code(get_resp) == 404

    patch_resp = await client.patch(f"/api/v1/agents/{agent_id}/agent-details", json={"name": "Hijacked"})
    assert code(patch_resp) == 404

    list_resp = await client.get("/api/v1/agents")
    ids = {a["id"] for a in data(list_resp)}
    assert agent_id not in ids


async def test_admin_assigning_a_developer_grants_access(client):
    set_auth(client.app, "dev-1", "org-1", role=Role.DEVELOPER)
    agent_id = await _create_agent(client, "Dev1 Agent")

    set_auth(client.app, "admin-1", "org-1", role=Role.ADMIN)
    assign_resp = await client.post(f"/api/v1/agents/{agent_id}/assignments", json={"user_id": "dev-2"})
    assert code(assign_resp) == 201
    assert "dev-2" in data(assign_resp)

    set_auth(client.app, "dev-2", "org-1", role=Role.DEVELOPER)
    get_resp = await client.get(f"/api/v1/agents/{agent_id}")
    assert code(get_resp) == 200

    patch_resp = await client.patch(f"/api/v1/agents/{agent_id}/agent-details", json={"name": "Now Editable"})
    assert code(patch_resp) == 200

    list_resp = await client.get("/api/v1/agents")
    ids = {a["id"] for a in data(list_resp)}
    assert agent_id in ids

    set_auth(client.app, "admin-1", "org-1", role=Role.ADMIN)
    unassign_resp = await client.delete(f"/api/v1/agents/{agent_id}/assignments/dev-2")
    assert code(unassign_resp) == 200
    assert "dev-2" not in data(unassign_resp)

    set_auth(client.app, "dev-2", "org-1", role=Role.DEVELOPER)
    get_resp = await client.get(f"/api/v1/agents/{agent_id}")
    assert code(get_resp) == 404


async def test_cloning_an_agent_auto_assigns_the_developer(client):
    set_auth(client.app, "admin-1", "org-1", role=Role.ADMIN)
    agent_id = await _create_agent(client, "Source")

    set_auth(client.app, "admin-1", "org-1", role=Role.ADMIN)
    await client.post(f"/api/v1/agents/{agent_id}/assignments", json={"user_id": "dev-1"})

    set_auth(client.app, "dev-1", "org-1", role=Role.DEVELOPER)
    clone_resp = await client.post(f"/api/v1/agents/{agent_id}/clone")
    assert code(clone_resp) == 201
    clone_id = data(clone_resp)["id"]

    get_resp = await client.get(f"/api/v1/agents/{clone_id}")
    assert code(get_resp) == 200


async def test_developer_cannot_manage_assignments_even_on_own_agent(client):
    set_auth(client.app, "dev-1", "org-1", role=Role.DEVELOPER)
    agent_id = await _create_agent(client, "Dev Agent")

    assign_resp = await client.post(f"/api/v1/agents/{agent_id}/assignments", json={"user_id": "dev-2"})
    assert code(assign_resp) == 403

    list_resp = await client.get(f"/api/v1/agents/{agent_id}/assignments")
    assert code(list_resp) == 403


async def test_qa_cannot_manage_assignments(client):
    set_auth(client.app, "admin-1", "org-1", role=Role.ADMIN)
    agent_id = await _create_agent(client, "Some Agent")

    set_auth(client.app, "qa-1", "org-1", role=Role.QA)
    assign_resp = await client.post(f"/api/v1/agents/{agent_id}/assignments", json={"user_id": "dev-1"})
    assert code(assign_resp) == 403


# --- Admin: unaffected ----------------------------------------------------


async def test_admin_has_full_access_regardless_of_assignment(client):
    set_auth(client.app, "dev-1", "org-1", role=Role.DEVELOPER)
    agent_id = await _create_agent(client, "Dev Agent")

    set_auth(client.app, "admin-1", "org-1", role=Role.ADMIN)
    get_resp = await client.get(f"/api/v1/agents/{agent_id}")
    assert code(get_resp) == 200

    patch_resp = await client.patch(f"/api/v1/agents/{agent_id}/agent-details", json={"name": "Admin Edit"})
    assert code(patch_resp) == 200

    delete_resp = await client.delete(f"/api/v1/agents/{agent_id}")
    assert code(delete_resp) == 200
