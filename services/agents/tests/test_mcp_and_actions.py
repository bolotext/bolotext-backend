import pytest

from tests.factories import code, data, set_auth

pytestmark = pytest.mark.asyncio


async def test_mcp_section_patch_does_not_clobber_actions(client):
    set_auth(client.app, "user-1", "org-1")
    create_resp = await client.post("/api/v1/agents", json={"name": "Tool Agent"})
    agent_id = data(create_resp)["id"]

    await client.patch(
        f"/api/v1/agents/{agent_id}/actions",
        json={
            "actions": [
                {
                    "name": "reserve_slot",
                    "description": "Reserves an appointment slot.",
                    "endpoint_url": "https://example.com/api/slots/reserve",
                }
            ]
        },
    )
    await client.patch(
        f"/api/v1/agents/{agent_id}/mcp",
        json={
            "servers": [
                {
                    "server_id": "crm-mcp",
                    "name": "CRM Tools",
                    "url": "https://mcp.example.com/crm/mcp",
                    "allowed_tools": ["lookup_customer"],
                }
            ]
        },
    )

    resp = await client.get(f"/api/v1/agents/{agent_id}")
    body = data(resp)
    assert body["mcp"]["servers"][0]["server_id"] == "crm-mcp"
    assert body["mcp"]["servers"][0]["transport"] == "streamable_http"
    # The earlier actions patch is untouched by the later mcp patch.
    assert body["actions"]["actions"][0]["name"] == "reserve_slot"


async def test_clone_copies_mcp_and_actions_sections(client):
    set_auth(client.app, "user-1", "org-1")
    create_resp = await client.post("/api/v1/agents", json={"name": "Original With Tools"})
    agent_id = data(create_resp)["id"]
    await client.patch(
        f"/api/v1/agents/{agent_id}/mcp",
        json={"servers": [{"server_id": "s1", "name": "S1", "url": "https://mcp.example.com/s1"}]},
    )

    clone_resp = await client.post(f"/api/v1/agents/{agent_id}/clone")
    assert code(clone_resp) == 201
    clone = data(clone_resp)
    assert clone["mcp"]["servers"][0]["server_id"] == "s1"
