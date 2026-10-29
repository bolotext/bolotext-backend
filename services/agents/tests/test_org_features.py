"""A Super Admin decides which product areas (voice agents, WhatsApp, SMS) an
organization may use; the Agents service enforces it."""

from common.enums import Role

from tests.factories import code, data, error_type, set_auth


async def _post_agent(client, channel):
    return await client.post("/api/v1/whatsapp/agents", json={"name": f"{channel} agent", "channel": channel})


async def test_voice_agents_need_the_voice_feature(client):
    set_auth(client.app, "u1", "org-1", features=["whatsapp", "sms"])
    assert error_type(await client.get("/api/v1/agents")) == "FORBIDDEN"
    assert error_type(await client.post("/api/v1/agents", json={"name": "Nope"})) == "FORBIDDEN"
    set_auth(client.app, "u1", "org-1", features=["voice_agents"])
    assert code(await client.post("/api/v1/agents", json={"name": "Yes"})) == 201
    assert code(await client.get("/api/v1/agents")) == 200
    # Super Admins and unrestricted contexts are never blocked.
    set_auth(client.app, "sa", "org-1", role=Role.SUPER_ADMIN, features=["sms"])
    assert code(await client.get("/api/v1/agents")) == 200


async def test_whatsapp_and_sms_are_gated_per_channel(client):
    set_auth(client.app, "u1", "org-1", features=["whatsapp"])
    wa = data(await _post_agent(client, "whatsapp"))["id"]
    assert error_type(await _post_agent(client, "sms")) == "FORBIDDEN"
    assert error_type(await client.get("/api/v1/whatsapp/agents", params={"channel": "sms"})) == "FORBIDDEN"
    assert code(await client.get("/api/v1/whatsapp/agents", params={"channel": "whatsapp"})) == 200
    assert code(await client.get("/api/v1/agents")) != 200  # voice is off too

    # Access follows the agent's channel, so an org that loses SMS loses its SMS agents.
    set_auth(client.app, "u1", "org-1", features=["whatsapp", "sms"])
    sms = data(await _post_agent(client, "sms"))["id"]
    set_auth(client.app, "u1", "org-1", features=["whatsapp"])
    assert error_type(await client.get(f"/api/v1/whatsapp/agents/{sms}")) == "FORBIDDEN"
    assert error_type(await client.get(f"/api/v1/whatsapp/agents/{sms}/contacts")) == "FORBIDDEN"
    assert code(await client.get(f"/api/v1/whatsapp/agents/{wa}")) == 200

    # The shared Twilio settings need at least one messaging feature.
    assert code(await client.get("/api/v1/whatsapp/settings")) == 200
    set_auth(client.app, "u1", "org-1", features=["voice_agents"])
    assert error_type(await client.get("/api/v1/whatsapp/settings")) == "FORBIDDEN"
