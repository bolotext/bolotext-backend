import pytest

from tests.factories import code, data, error_type, set_auth

pytestmark = pytest.mark.asyncio


async def _create_agent(client, name: str = "Prompt Versioned Agent") -> str:
    set_auth(client.app, "user-1", "org-1")
    create_resp = await client.post("/api/v1/agents", json={"name": name})
    return data(create_resp)["id"]


async def _create_version(client, agent_id: str, prompt_key: str, system_prompt: str = "text", description: str | None = None):
    return await client.post(
        f"/api/v1/agents/{agent_id}/prompt/versions",
        json={"prompt_key": prompt_key, "prompt_description": description, "system_prompt": system_prompt},
    )


async def test_creating_a_version_returns_it(client):
    agent_id = await _create_agent(client)

    resp = await _create_version(client, agent_id, "prompt_v1", "Be helpful.", "Original tone")
    assert code(resp) == 201
    body = data(resp)
    assert body["prompt_key"] == "prompt_v1"
    assert body["prompt_description"] == "Original tone"
    assert body["system_prompt"] == "Be helpful."
    assert body["created_by"] == "user-1"


async def test_duplicate_prompt_key_is_rejected(client):
    agent_id = await _create_agent(client)
    await _create_version(client, agent_id, "prompt_v1")

    resp = await _create_version(client, agent_id, "prompt_v1")
    assert code(resp) == 409
    assert error_type(resp) == "CONFLICT"


async def test_sixth_version_is_rejected_until_one_is_deleted(client):
    agent_id = await _create_agent(client)
    for i in range(1, 6):
        resp = await _create_version(client, agent_id, f"prompt_v{i}")
        assert code(resp) == 201

    versions_resp = await client.get(f"/api/v1/agents/{agent_id}/prompt/versions")
    assert len(data(versions_resp)) == 5

    blocked_resp = await _create_version(client, agent_id, "prompt_v6")
    assert code(blocked_resp) == 422
    assert error_type(blocked_resp) == "UNPROCESSABLE_ENTITY"
    assert blocked_resp.json()["errors"]["max_versions"] == 5

    delete_resp = await client.delete(f"/api/v1/agents/{agent_id}/prompt/versions/prompt_v1")
    assert code(delete_resp) == 200

    retry_resp = await _create_version(client, agent_id, "prompt_v6")
    assert code(retry_resp) == 201

    versions_resp = await client.get(f"/api/v1/agents/{agent_id}/prompt/versions")
    assert len(data(versions_resp)) == 5


async def test_replacing_a_version_changes_only_its_text(client):
    agent_id = await _create_agent(client)
    await _create_version(client, agent_id, "prompt_v1", "Old text", "Old description")

    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/prompt/versions",
        json={"prompt_key": "prompt_v1", "system_prompt": "New text"},
    )
    assert code(resp) == 200
    body = data(resp)
    assert body["system_prompt"] == "New text"
    assert body["prompt_key"] == "prompt_v1"
    # prompt_description isn't settable through this route — untouched.
    assert body["prompt_description"] == "Old description"


async def test_replacing_a_missing_version_is_404(client):
    agent_id = await _create_agent(client)
    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/prompt/versions", json={"prompt_key": "does-not-exist", "system_prompt": "x"}
    )
    assert code(resp) == 404


async def test_deleting_a_missing_version_is_404(client):
    agent_id = await _create_agent(client)
    resp = await client.delete(f"/api/v1/agents/{agent_id}/prompt/versions/does-not-exist")
    assert code(resp) == 404


async def test_deleting_a_version_never_touches_prompt_system_prompt(client):
    # Versions are an independent library — deleting one is always allowed,
    # regardless of what AgentPrompt.system_prompt currently holds (even if
    # it happens to equal the prompt_key being deleted, which means nothing
    # here; system_prompt is plain text, not a reference).
    agent_id = await _create_agent(client)
    await _create_version(client, agent_id, "prompt_v1", "Be helpful.")
    await client.patch(f"/api/v1/agents/{agent_id}/prompt/messages", json={"system_prompt": "prompt_v1"})

    resp = await client.delete(f"/api/v1/agents/{agent_id}/prompt/versions/prompt_v1")
    assert code(resp) == 200

    get_resp = await client.get(f"/api/v1/agents/{agent_id}")
    assert data(get_resp)["prompt"]["system_prompt"] == "prompt_v1"


async def test_versions_are_scoped_by_ownership(client):
    agent_id = await _create_agent(client)
    await _create_version(client, agent_id, "prompt_v1")

    set_auth(client.app, "user-b", "org-b")
    resp = await client.get(f"/api/v1/agents/{agent_id}/prompt/versions")
    assert code(resp) == 404


async def test_agent_prompt_system_prompt_is_independent_of_versions(client):
    agent_id = await _create_agent(client)
    await _create_version(client, agent_id, "prompt_v1", "A saved snippet, never used below.")

    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/prompt/messages", json={"system_prompt": "Completely different text."}
    )
    assert code(resp) == 200
    assert data(resp)["prompt"]["system_prompt"] == "Completely different text."

    get_resp = await client.get(f"/api/v1/agents/{agent_id}")
    assert data(get_resp)["prompt"]["system_prompt"] == "Completely different text."

    # The version is untouched and still listed.
    versions = data(await client.get(f"/api/v1/agents/{agent_id}/prompt/versions"))
    assert versions[0]["system_prompt"] == "A saved snippet, never used below."
