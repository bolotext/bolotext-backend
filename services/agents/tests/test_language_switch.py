import pytest

from tests.factories import code, data, error_type, set_auth

pytestmark = pytest.mark.asyncio


async def _create_agent(client, languages: list[str] | None = None, name: str = "Test Agent") -> str:
    set_auth(client.app, "user-1", "org-1")
    resp = await client.post("/api/v1/agents", json={"name": name})
    assert code(resp) == 201
    agent_id = data(resp)["id"]
    if languages is not None:
        await client.put(f"/api/v1/agents/{agent_id}/languages", json={"languages": languages})
    return agent_id


async def test_preview_is_none_for_a_single_language_agent(client):
    agent_id = await _create_agent(client, languages=["en-IN"])

    resp = await client.get(f"/api/v1/agents/{agent_id}/prompt/language-switch-preview")
    assert code(resp) == 200
    body = data(resp)
    assert body["mode"] == "explicit"
    assert body["prompt"] is None


async def test_explicit_preview_only_mentions_configured_languages(client):
    agent_id = await _create_agent(client, languages=["en-IN", "hi-IN"])

    resp = await client.get(f"/api/v1/agents/{agent_id}/prompt/language-switch-preview")
    assert code(resp) == 200
    prompt = data(resp)["prompt"]
    assert prompt is not None
    assert "Hindi" in prompt
    assert "English" in prompt
    assert "Kannada" not in prompt
    assert "Tamil" not in prompt
    assert "Telugu" not in prompt


async def test_implicit_mode_renders_a_different_template(client):
    agent_id = await _create_agent(client, languages=["en-IN", "hi-IN", "kn-IN"])
    await client.patch(f"/api/v1/agents/{agent_id}/prompt/language-switch", json={"language_switch_mode": "implicit"})

    resp = await client.get(f"/api/v1/agents/{agent_id}/prompt/language-switch-preview")
    body = data(resp)
    assert body["mode"] == "implicit"
    assert "Language Detection Agent" in body["prompt"]
    assert "Kannada" in body["prompt"]


async def test_custom_mode_requires_language_switch_prompt(client):
    agent_id = await _create_agent(client, languages=["en-IN", "hi-IN"])

    resp = await client.patch(f"/api/v1/agents/{agent_id}/prompt/language-switch", json={"language_switch_mode": "custom"})
    assert code(resp) == 422
    assert error_type(resp) == "UNPROCESSABLE_ENTITY"


async def test_custom_mode_with_prompt_is_accepted_and_returned_verbatim(client):
    agent_id = await _create_agent(client, languages=["en-IN", "hi-IN"])

    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/prompt/language-switch",
        json={"language_switch_mode": "custom", "language_switch_prompt": "Detect the language, custom rules."},
    )
    assert code(resp) == 200

    preview = data(await client.get(f"/api/v1/agents/{agent_id}/prompt/language-switch-preview"))
    assert preview["mode"] == "custom"
    assert preview["prompt"] == "Detect the language, custom rules."
