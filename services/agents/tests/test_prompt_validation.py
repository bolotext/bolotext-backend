import pytest

from tests.factories import code, data, error_type, set_auth

pytestmark = pytest.mark.asyncio


async def _create_agent(client, name: str = "Test Agent") -> str:
    set_auth(client.app, "user-1", "org-1")
    resp = await client.post("/api/v1/agents", json={"name": name})
    assert code(resp) == 201
    return data(resp)["id"]


async def _declare_pre_call_variables(client, agent_id: str, *names: str):
    return await client.put(
        f"/api/v1/agents/{agent_id}/pre-call-variables", json={"pre_call_variables": {n: "" for n in names}}
    )


async def test_prompt_with_undeclared_variable_is_rejected(client):
    agent_id = await _create_agent(client)
    await _declare_pre_call_variables(client, agent_id, "customer_name")

    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/prompt/messages",
        json={
            "welcome_message": "Hi {{customer_name}}, this is a reminder about {{due_amount}}.",
            "system_prompt": "",
            "ending_message": "Bye {{customer_name}}.",
        },
    )
    assert resp.status_code == 200
    assert code(resp) == 422
    assert error_type(resp) == "UNPROCESSABLE_ENTITY"
    assert resp.json()["errors"]["missing_variables"] == ["due_amount"]


async def test_prompt_with_all_variables_declared_is_accepted(client):
    agent_id = await _create_agent(client)
    await _declare_pre_call_variables(client, agent_id, "customer_name", "due_amount")

    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/prompt/messages",
        json={
            "welcome_message": "Hi {{customer_name}}, this is a reminder about {{due_amount}}.",
            "system_prompt": "Be polite.",
            "ending_message": "Bye {{customer_name}}.",
        },
    )
    assert resp.status_code == 200
    assert code(resp) == 200
    body = data(resp)
    assert body["prompt"]["pre_call_variables"] == {"customer_name": "", "due_amount": ""}
    assert body["prompt"]["system_prompt"] == "Be polite."


async def test_system_prompt_is_stored_directly_without_referencing_a_version(client):
    # No system_prompt_versions row exists at all here — system_prompt is
    # free text, not gated on the version library in any way.
    agent_id = await _create_agent(client)

    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/prompt/messages",
        json={"welcome_message": "Hi.", "system_prompt": "Whatever text I like.", "ending_message": "Bye."},
    )
    assert code(resp) == 200
    assert data(resp)["prompt"]["system_prompt"] == "Whatever text I like."


async def test_test_endpoint_renders_prompt_with_sample_values(client):
    agent_id = await _create_agent(client)
    await _declare_pre_call_variables(client, agent_id, "customer_name", "due_amount")
    await client.patch(
        f"/api/v1/agents/{agent_id}/prompt/messages",
        json={
            "welcome_message": "Hi {{customer_name}}.",
            "system_prompt": "Discuss {{due_amount}}.",
            "ending_message": "Bye {{customer_name}}.",
        },
    )

    resp = await client.post(
        f"/api/v1/agents/{agent_id}/test", json={"sample_values": {"customer_name": "Ramesh"}}
    )
    assert resp.status_code == 200
    assert code(resp) == 200
    body = data(resp)
    assert body["welcome_message"] == "Hi Ramesh."
    assert body["system_prompt"] == "Discuss <due_amount>."
    assert body["ending_message"] == "Bye Ramesh."
    assert body["sample_values_used"] == {"customer_name": "Ramesh", "due_amount": "<due_amount>"}
