import pytest

from tests.factories import code, data, set_auth

pytestmark = pytest.mark.asyncio


async def _create_agent(client, name: str = "Precall Agent") -> str:
    set_auth(client.app, "user-1", "org-1")
    resp = await client.post("/api/v1/agents", json={"name": name})
    return data(resp)["id"]


async def test_defaults_to_empty(client):
    agent_id = await _create_agent(client)
    assert data(await client.get(f"/api/v1/agents/{agent_id}"))["prompt"]["pre_call_variables"] == {}


async def test_put_replaces_the_whole_mapping(client):
    agent_id = await _create_agent(client)

    resp = await client.put(
        f"/api/v1/agents/{agent_id}/pre-call-variables",
        json={"pre_call_variables": {"customer_name": "", "customer_id": "", "order_id": "", "company_name": "Acme"}},
    )
    assert code(resp) == 200
    assert data(resp)["prompt"]["pre_call_variables"] == {
        "customer_name": "",
        "customer_id": "",
        "order_id": "",
        "company_name": "Acme",
    }

    # A second PUT replaces, not merges.
    resp2 = await client.put(
        f"/api/v1/agents/{agent_id}/pre-call-variables", json={"pre_call_variables": {"customer_name": "Ramesh"}}
    )
    assert data(resp2)["prompt"]["pre_call_variables"] == {"customer_name": "Ramesh"}


async def test_test_endpoint_falls_back_to_pre_call_variable_defaults(client):
    agent_id = await _create_agent(client)
    await client.put(
        f"/api/v1/agents/{agent_id}/pre-call-variables",
        json={"pre_call_variables": {"customer_name": "Ramesh Kumar", "company_name": "Acme Bank"}},
    )
    await client.patch(
        f"/api/v1/agents/{agent_id}/prompt/messages",
        json={"welcome_message": "Hi {{customer_name}}, welcome to {{company_name}}."},
    )

    # No sample_values at all — everything comes from pre_call_variables.
    resp = await client.post(f"/api/v1/agents/{agent_id}/test", json={})
    assert code(resp) == 200
    assert data(resp)["welcome_message"] == "Hi Ramesh Kumar, welcome to Acme Bank."

    # An explicit sample_value overrides the configured default.
    resp2 = await client.post(
        f"/api/v1/agents/{agent_id}/test", json={"sample_values": {"customer_name": "Priya"}}
    )
    body2 = data(resp2)
    assert body2["welcome_message"] == "Hi Priya, welcome to Acme Bank."


async def test_custom_language_switch_prompt_resolves_pre_call_variables(client):
    agent_id = await _create_agent(client)
    await client.put(
        f"/api/v1/agents/{agent_id}/pre-call-variables", json={"pre_call_variables": {"company_name": "Acme Bank"}}
    )
    await client.patch(
        f"/api/v1/agents/{agent_id}/prompt/language-switch",
        json={"language_switch_mode": "custom", "language_switch_prompt": "You are {{company_name}}'s assistant."},
    )

    resp = await client.get(f"/api/v1/agents/{agent_id}/prompt/language-switch-preview")
    assert code(resp) == 200
    assert data(resp)["prompt"] == "You are Acme Bank's assistant."
