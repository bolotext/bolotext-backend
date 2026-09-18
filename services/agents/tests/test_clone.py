import pytest

from tests.factories import code, data, set_auth

pytestmark = pytest.mark.asyncio


async def test_clone_creates_a_new_active_agent_with_copied_sections(client):
    set_auth(client.app, "user-1", "org-1")
    create_resp = await client.post("/api/v1/agents", json={"name": "Original"})
    agent_id = data(create_resp)["id"]
    await client.patch(f"/api/v1/agents/{agent_id}/llm", json={"provider_id": "openai", "model_id": "gpt-4o-mini"})

    clone_resp = await client.post(f"/api/v1/agents/{agent_id}/clone")
    assert code(clone_resp) == 201
    clone = data(clone_resp)
    assert clone["id"] != agent_id
    assert clone["status"] == "active"
    assert clone["agent_details"]["name"] == "Original (Copy)"
    assert clone["llm"]["provider_id"] == "openai"

    # The source agent is untouched.
    original = data(await client.get(f"/api/v1/agents/{agent_id}"))
    assert original["agent_details"]["name"] == "Original"
