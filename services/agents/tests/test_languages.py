import pytest

from tests.factories import code, data, set_auth

pytestmark = pytest.mark.asyncio


async def test_new_agent_defaults_to_english_only(client):
    set_auth(client.app, "user-1", "org-1")
    create_resp = await client.post("/api/v1/agents", json={"name": "Fresh"})
    assert code(create_resp) == 201
    assert data(create_resp)["languages"] == ["en-IN"]


async def test_languages_key_in_create_payload_is_ignored(client):
    # Creating an agent never asks for languages — a client sending it
    # anyway is silently ignored, not an error, and not applied.
    set_auth(client.app, "user-1", "org-1")
    create_resp = await client.post(
        "/api/v1/agents", json={"name": "Sneaky", "languages": ["hi-IN", "ta-IN"]}
    )
    assert code(create_resp) == 201
    assert data(create_resp)["languages"] == ["en-IN"]


async def test_dedicated_endpoint_configures_languages(client):
    set_auth(client.app, "user-1", "org-1")
    create_resp = await client.post("/api/v1/agents", json={"name": "Configurable"})
    agent_id = data(create_resp)["id"]

    resp = await client.put(f"/api/v1/agents/{agent_id}/languages", json={"languages": ["en-IN", "hi-IN"]})
    assert code(resp) == 200
    assert data(resp)["languages"] == ["en-IN", "hi-IN"]

    get_resp = await client.get(f"/api/v1/agents/{agent_id}")
    assert data(get_resp)["languages"] == ["en-IN", "hi-IN"]


async def test_empty_languages_list_is_rejected(client):
    set_auth(client.app, "user-1", "org-1")
    create_resp = await client.post("/api/v1/agents", json={"name": "NoLangs"})
    agent_id = data(create_resp)["id"]

    resp = await client.put(f"/api/v1/agents/{agent_id}/languages", json={"languages": []})
    assert code(resp) == 422
    assert resp.json()["errors"]["type"] == "UNPROCESSABLE_ENTITY"
