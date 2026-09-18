import pytest

from tests.factories import code, data, error_type, set_auth

pytestmark = pytest.mark.asyncio


async def _create_agent(client, name: str = "Status Agent") -> str:
    set_auth(client.app, "user-1", "org-1")
    resp = await client.post("/api/v1/agents", json={"name": name})
    assert code(resp) == 201
    return data(resp)["id"]


async def test_new_agent_is_active_by_default(client):
    agent_id = await _create_agent(client)
    assert data(await client.get(f"/api/v1/agents/{agent_id}"))["status"] == "active"


async def test_deactivate_then_activate(client):
    agent_id = await _create_agent(client)

    deactivate_resp = await client.post(f"/api/v1/agents/{agent_id}/deactivate")
    assert code(deactivate_resp) == 200
    assert data(deactivate_resp)["status"] == "inactive"

    get_resp = await client.get(f"/api/v1/agents/{agent_id}")
    assert data(get_resp)["status"] == "inactive"

    activate_resp = await client.post(f"/api/v1/agents/{agent_id}/activate")
    assert code(activate_resp) == 200
    assert data(activate_resp)["status"] == "active"


async def test_status_endpoint_sets_an_explicit_value(client):
    agent_id = await _create_agent(client)

    resp = await client.patch(f"/api/v1/agents/{agent_id}/status", json={"status": "inactive"})
    assert code(resp) == 200
    assert data(resp)["status"] == "inactive"


async def test_status_endpoint_rejects_an_unknown_value(client):
    agent_id = await _create_agent(client)

    resp = await client.patch(f"/api/v1/agents/{agent_id}/status", json={"status": "draft"})
    assert error_type(resp) == "VALIDATION_ERROR"


async def test_status_changes_are_scoped_to_the_owning_org(client):
    agent_id = await _create_agent(client)

    set_auth(client.app, "user-2", "org-2")
    resp = await client.post(f"/api/v1/agents/{agent_id}/deactivate")
    assert code(resp) == 404


async def test_publish_route_no_longer_exists(client):
    agent_id = await _create_agent(client)
    resp = await client.post(f"/api/v1/agents/{agent_id}/publish")
    assert resp.status_code == 404
