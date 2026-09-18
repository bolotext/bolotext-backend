import pytest

from tests.factories import code, data, set_auth

pytestmark = pytest.mark.asyncio


async def test_publish_fails_with_missing_sections_on_a_fresh_draft(client):
    set_auth(client.app, "user-1", "org-1")
    create_resp = await client.post("/api/v1/agents", json={"name": "Fresh Draft"})
    agent_id = data(create_resp)["id"]

    resp = await client.post(f"/api/v1/agents/{agent_id}/publish")
    assert resp.status_code == 200
    assert code(resp) == 422
    missing = set(resp.json()["errors"]["missing_sections"])
    assert missing == {"prompt", "transcriber", "llm", "voice_persona"}


async def test_publish_succeeds_once_required_sections_are_filled(client):
    set_auth(client.app, "user-1", "org-1")
    create_resp = await client.post("/api/v1/agents", json={"name": "Ready Agent"})
    agent_id = data(create_resp)["id"]

    await client.patch(
        f"/api/v1/agents/{agent_id}/prompt",
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

    resp = await client.post(f"/api/v1/agents/{agent_id}/publish")
    assert code(resp) == 200
    assert data(resp)["status"] == "published"


async def test_clone_creates_a_new_draft_with_copied_sections(client):
    set_auth(client.app, "user-1", "org-1")
    create_resp = await client.post("/api/v1/agents", json={"name": "Original"})
    agent_id = data(create_resp)["id"]
    await client.patch(f"/api/v1/agents/{agent_id}/llm", json={"provider_id": "openai", "model_id": "gpt-4o-mini"})

    clone_resp = await client.post(f"/api/v1/agents/{agent_id}/clone")
    assert code(clone_resp) == 201
    clone = data(clone_resp)
    assert clone["id"] != agent_id
    assert clone["status"] == "draft"
    assert clone["agent_details"]["name"] == "Original (Copy)"
    assert clone["llm"]["provider_id"] == "openai"

    # The source agent is untouched.
    original = data(await client.get(f"/api/v1/agents/{agent_id}"))
    assert original["agent_details"]["name"] == "Original"
