import pytest

from tests.factories import code, data, error_type, set_auth

pytestmark = pytest.mark.asyncio


async def _create_agent(client, name: str = "Endpoint Agent") -> str:
    set_auth(client.app, "user-1", "org-1")
    resp = await client.post("/api/v1/agents", json={"name": name})
    return data(resp)["id"]


async def test_generic_prompt_route_no_longer_exists(client):
    agent_id = await _create_agent(client)

    resp = await client.patch(f"/api/v1/agents/{agent_id}/prompt", json={"welcome_message": "Hi."})
    # 404, not 405: no route registers this exact path any more (unlike a
    # method removed from an otherwise-still-registered path) — every
    # AgentPrompt field is covered by .../prompt/messages,
    # .../prompt/language-switch, .../pre-call-variables, or .../dynamic-message.
    assert resp.status_code == 404


async def test_messages_endpoint_updates_only_the_three_message_fields(client):
    agent_id = await _create_agent(client)
    # Set pre_call_variables and language_switch_mode via their own routes first.
    await client.put(
        f"/api/v1/agents/{agent_id}/pre-call-variables", json={"pre_call_variables": {"customer_name": ""}}
    )
    await client.patch(f"/api/v1/agents/{agent_id}/prompt/language-switch", json={"language_switch_mode": "implicit"})

    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/prompt/messages",
        json={"welcome_message": "Hi {{customer_name}}.", "system_prompt": "Be helpful.", "ending_message": "Bye."},
    )
    assert code(resp) == 200
    body = data(resp)
    assert body["prompt"]["welcome_message"] == "Hi {{customer_name}}."
    assert body["prompt"]["system_prompt"] == "Be helpful."
    assert body["prompt"]["ending_message"] == "Bye."
    # Untouched by this endpoint.
    assert body["prompt"]["pre_call_variables"] == {"customer_name": ""}
    assert body["prompt"]["language_switch_mode"] == "implicit"


async def test_messages_endpoint_accepts_any_system_prompt_text(client):
    # There's no system_prompt_versions row here at all — nothing to
    # reference, no 422 for "unknown" text.
    agent_id = await _create_agent(client)

    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/prompt/messages",
        json={"system_prompt": "Not a prompt_key, just text."},
    )
    assert code(resp) == 200
    assert data(resp)["prompt"]["system_prompt"] == "Not a prompt_key, just text."


async def test_messages_endpoint_still_validates_pre_call_variables(client):
    agent_id = await _create_agent(client)

    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/prompt/messages",
        json={"welcome_message": "Hi {{customer_name}}."},
    )
    assert code(resp) == 422
    assert resp.json()["errors"]["missing_variables"] == ["customer_name"]


async def test_language_switch_endpoint_updates_only_those_fields(client):
    agent_id = await _create_agent(client)
    await client.patch(f"/api/v1/agents/{agent_id}/prompt/messages", json={"welcome_message": "Hi."})

    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/prompt/language-switch",
        json={"language_switch_mode": "implicit", "min_words_for_lang_switch": 3},
    )
    assert code(resp) == 200
    body = data(resp)
    assert body["prompt"]["language_switch_mode"] == "implicit"
    assert body["prompt"]["min_words_for_lang_switch"] == 3
    # Untouched by this endpoint.
    assert body["prompt"]["welcome_message"] == "Hi."


async def test_language_switch_endpoint_requires_prompt_for_custom_mode(client):
    agent_id = await _create_agent(client)

    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/prompt/language-switch", json={"language_switch_mode": "custom"}
    )
    assert code(resp) == 422
    assert error_type(resp) == "UNPROCESSABLE_ENTITY"
