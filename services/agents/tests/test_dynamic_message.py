import pytest

from tests.factories import code, data, set_auth

pytestmark = pytest.mark.asyncio


async def _create_agent(client, name: str = "Dynamic Message Agent") -> str:
    set_auth(client.app, "user-1", "org-1")
    resp = await client.post("/api/v1/agents", json={"name": name})
    return data(resp)["id"]


async def test_defaults_to_disabled(client):
    agent_id = await _create_agent(client)
    resp = await client.get(f"/api/v1/agents/{agent_id}/dynamic-message")
    assert code(resp) == 200
    body = data(resp)
    assert body["dynamic_message_enabled"] is False
    assert body["method"] == "POST"
    assert body["url"] is None
    assert body["headers"] == {}


async def test_create_sets_the_full_configuration(client):
    agent_id = await _create_agent(client)

    resp = await client.post(
        f"/api/v1/agents/{agent_id}/dynamic-message",
        json={
            "dynamic_message_enabled": True,
            "method": "POST",
            "url": "https://example.com/api",
            "headers": {"Authorization": "Bearer xxx", "Content-Type": "application/json"},
        },
    )
    assert code(resp) == 201
    section = data(resp)["prompt"]["dynamic_message"]
    assert section["dynamic_message_enabled"] is True
    assert section["url"] == "https://example.com/api"
    assert section["headers"]["Authorization"] == "Bearer xxx"

    get_resp = await client.get(f"/api/v1/agents/{agent_id}/dynamic-message")
    assert data(get_resp)["url"] == "https://example.com/api"


async def test_update_partially_changes_fields(client):
    agent_id = await _create_agent(client)
    await client.post(
        f"/api/v1/agents/{agent_id}/dynamic-message",
        json={"dynamic_message_enabled": True, "method": "GET", "url": "https://a.example.com", "headers": {}},
    )

    resp = await client.patch(f"/api/v1/agents/{agent_id}/dynamic-message", json={"method": "PUT"})
    assert code(resp) == 200
    section = data(resp)["prompt"]["dynamic_message"]
    assert section["method"] == "PUT"
    # Untouched fields keep their previous values.
    assert section["url"] == "https://a.example.com"
    assert section["dynamic_message_enabled"] is True


async def test_invalid_method_is_rejected(client):
    agent_id = await _create_agent(client)
    resp = await client.post(
        f"/api/v1/agents/{agent_id}/dynamic-message",
        json={"dynamic_message_enabled": False, "method": "OPTIONS", "url": None, "headers": {}},
    )
    assert resp.json()["errors"]["type"] == "VALIDATION_ERROR"


async def test_enable_and_disable_shortcuts(client):
    agent_id = await _create_agent(client)

    enable_resp = await client.post(f"/api/v1/agents/{agent_id}/dynamic-message/enable")
    assert code(enable_resp) == 200
    assert data(enable_resp)["prompt"]["dynamic_message"]["dynamic_message_enabled"] is True

    disable_resp = await client.post(f"/api/v1/agents/{agent_id}/dynamic-message/disable")
    assert code(disable_resp) == 200
    assert data(disable_resp)["prompt"]["dynamic_message"]["dynamic_message_enabled"] is False


async def test_delete_resets_to_defaults(client):
    agent_id = await _create_agent(client)
    await client.post(
        f"/api/v1/agents/{agent_id}/dynamic-message",
        json={"dynamic_message_enabled": True, "method": "POST", "url": "https://example.com", "headers": {}},
    )

    resp = await client.delete(f"/api/v1/agents/{agent_id}/dynamic-message")
    assert code(resp) == 200
    section = data(resp)["prompt"]["dynamic_message"]
    assert section["dynamic_message_enabled"] is False
    assert section["url"] is None
