import pytest

from tests.factories import code, data, error_type, set_auth

pytestmark = pytest.mark.asyncio


async def _create_agent(client, name: str = "Test Agent") -> str:
    set_auth(client.app, "user-1", "org-1")
    resp = await client.post("/api/v1/agents", json={"name": name})
    assert code(resp) == 201
    return data(resp)["id"]


async def test_prompt_with_undeclared_variable_is_rejected(client):
    agent_id = await _create_agent(client)

    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/prompt",
        json={
            "welcome_message": "Hi {{customer_name}}, this is a reminder about {{due_amount}}.",
            "system_prompt": "Be polite.",
            "ending_message": "Bye {{customer_name}}.",
            "dynamic_variables": ["customer_name"],
        },
    )
    assert resp.status_code == 200
    assert code(resp) == 422
    assert error_type(resp) == "UNPROCESSABLE_ENTITY"
    assert resp.json()["errors"]["missing_variables"] == ["due_amount"]


async def test_prompt_with_all_variables_declared_is_accepted(client):
    agent_id = await _create_agent(client)

    resp = await client.patch(
        f"/api/v1/agents/{agent_id}/prompt",
        json={
            "welcome_message": "Hi {{customer_name}}, this is a reminder about {{due_amount}}.",
            "system_prompt": "Be polite.",
            "ending_message": "Bye {{customer_name}}.",
            "dynamic_variables": ["customer_name", "due_amount"],
        },
    )
    assert resp.status_code == 200
    assert code(resp) == 200
    body = data(resp)
    assert body["prompt"]["dynamic_variables"] == ["customer_name", "due_amount"]


async def test_prompt_placeholders_are_also_validated_on_full_replace(client):
    agent_id = await _create_agent(client)

    resp = await client.put(
        f"/api/v1/agents/{agent_id}",
        json={
            "agent_details": {"name": "Test Agent"},
            "prompt": {
                "welcome_message": "Hi {{customer_name}}.",
                "system_prompt": "Be polite.",
                "ending_message": "Bye.",
                "dynamic_variables": [],
            },
        },
    )
    assert resp.status_code == 200
    assert code(resp) == 422
    assert resp.json()["errors"]["missing_variables"] == ["customer_name"]


async def test_test_endpoint_renders_prompt_with_sample_values(client):
    agent_id = await _create_agent(client)
    await client.patch(
        f"/api/v1/agents/{agent_id}/prompt",
        json={
            "welcome_message": "Hi {{customer_name}}.",
            "system_prompt": "Discuss {{due_amount}}.",
            "ending_message": "Bye {{customer_name}}.",
            "dynamic_variables": ["customer_name", "due_amount"],
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
