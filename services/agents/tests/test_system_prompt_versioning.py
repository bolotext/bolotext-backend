import pytest

from tests.factories import code, data, error_type, set_auth

pytestmark = pytest.mark.asyncio


async def _create_agent(client, name: str = "Prompt Versioned Agent") -> str:
    set_auth(client.app, "user-1", "org-1")
    create_resp = await client.post("/api/v1/agents", json={"name": name})
    return data(create_resp)["id"]


async def _set_system_prompt(client, agent_id: str, system_prompt: str):
    return await client.patch(f"/api/v1/agents/{agent_id}/prompt", json={"system_prompt": system_prompt})


async def test_changing_system_prompt_records_a_version(client):
    agent_id = await _create_agent(client)
    await _set_system_prompt(client, agent_id, "v1 prompt")

    resp = await client.get(f"/api/v1/agents/{agent_id}/prompt/versions")
    assert code(resp) == 200
    versions = data(resp)
    assert len(versions) == 1
    assert versions[0]["version"] == 1
    assert versions[0]["system_prompt"] == "v1 prompt"
    assert versions[0]["created_by"] == "user-1"


async def test_saving_the_same_system_prompt_again_does_not_add_a_version(client):
    agent_id = await _create_agent(client)
    await _set_system_prompt(client, agent_id, "same prompt")
    await _set_system_prompt(client, agent_id, "same prompt")

    resp = await client.get(f"/api/v1/agents/{agent_id}/prompt/versions")
    assert len(data(resp)) == 1


async def test_editing_other_prompt_fields_does_not_touch_versions(client):
    agent_id = await _create_agent(client)
    await _set_system_prompt(client, agent_id, "stable prompt")

    await client.patch(f"/api/v1/agents/{agent_id}/prompt", json={"welcome_message": "Hi there."})

    resp = await client.get(f"/api/v1/agents/{agent_id}/prompt/versions")
    assert len(data(resp)) == 1


async def test_sixth_distinct_system_prompt_is_rejected_until_one_is_deleted(client):
    agent_id = await _create_agent(client)
    for i in range(1, 6):
        resp = await _set_system_prompt(client, agent_id, f"prompt v{i}")
        assert code(resp) == 200

    versions_resp = await client.get(f"/api/v1/agents/{agent_id}/prompt/versions")
    assert len(data(versions_resp)) == 5

    blocked_resp = await _set_system_prompt(client, agent_id, "prompt v6")
    assert code(blocked_resp) == 422
    assert error_type(blocked_resp) == "UNPROCESSABLE_ENTITY"
    assert blocked_resp.json()["errors"]["max_versions"] == 5
    assert "delete a previous version" in blocked_resp.json()["message"].lower()

    # The blocked save didn't go through — system_prompt is still v5.
    get_resp = await client.get(f"/api/v1/agents/{agent_id}")
    assert data(get_resp)["prompt"]["system_prompt"] == "prompt v5"

    # Deleting one frees a slot.
    delete_resp = await client.delete(f"/api/v1/agents/{agent_id}/prompt/versions/1")
    assert code(delete_resp) == 200

    retry_resp = await _set_system_prompt(client, agent_id, "prompt v6")
    assert code(retry_resp) == 200

    versions_resp = await client.get(f"/api/v1/agents/{agent_id}/prompt/versions")
    assert len(data(versions_resp)) == 5


async def test_deleting_a_missing_version_is_404(client):
    agent_id = await _create_agent(client)
    resp = await client.delete(f"/api/v1/agents/{agent_id}/prompt/versions/99")
    assert code(resp) == 404


async def test_prompt_versions_are_scoped_by_ownership(client):
    agent_id = await _create_agent(client)
    await _set_system_prompt(client, agent_id, "org a's prompt")

    set_auth(client.app, "user-b", "org-b")
    resp = await client.get(f"/api/v1/agents/{agent_id}/prompt/versions")
    assert code(resp) == 404


async def test_publish_no_longer_snapshots_the_whole_config(client):
    # Publishing is back to a plain status flip; there is no agent-level
    # version history any more (see system-prompt-only versioning above).
    agent_id = await _create_agent(client)
    await client.patch(
        f"/api/v1/agents/{agent_id}/prompt",
        json={"welcome_message": "Hi.", "system_prompt": "Be helpful.", "ending_message": "Bye."},
    )
    await client.patch(f"/api/v1/agents/{agent_id}/transcriber", json={"provider_id": "gnani"})
    await client.patch(f"/api/v1/agents/{agent_id}/llm", json={"provider_id": "openai", "model_id": "gpt-4o-mini"})
    await client.patch(
        f"/api/v1/agents/{agent_id}/voice-persona",
        json={"personas": [{"persona_id": "p1", "name": "Neha", "provider_id": "elevenlabs", "voice_id": "v1"}]},
    )

    resp = await client.post(f"/api/v1/agents/{agent_id}/publish")
    assert code(resp) == 200
    body = data(resp)
    assert body["status"] == "published"
    assert "published_version" not in body
