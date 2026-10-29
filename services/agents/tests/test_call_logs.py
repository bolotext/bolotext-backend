from common.enums import Role

from agents_service.call_logs.model import CallLog
from agents_service.core.deps import get_introspection
from agents_service.core.http_client import IntrospectResult
from tests.factories import code, data, error_type, set_auth

# Trimmed from what the voice runtime really posts.
INTERACTION = {
    "source": "website",
    "direction": "inbound",
    "details": {
        "duration": "0:24",
        "session_id": "RM_d3VNiPifoFwV",
        "start_at": "2026-10-29 12:32:02",
        "web_uuid": "testing-web-token",
        "from_phone": None,
        "to_phone": None,
        "recording_sid": None,
        "hangup_reason": {"end_reason": "client_initiated_disconnect", "type": "close"},
    },
    "test": True,
    "token_usage": {"llm_input_token": 742, "llm_output_token": 33, "average_e2e_latency": 1320},
    "interaction_journey": [
        {"id": "i1", "type": "agent_config_update", "instructions": "You are sona", "created_at": 1793257323.2},
        {"id": "i2", "type": "message", "role": "assistant", "content": ["नमस्ते"], "created_at": 1793257324.4},
        {"id": "i3", "type": "message", "role": "user", "content": ["आपका नाम क्या है?"], "created_at": 1793257339.1},
    ],
    "status": "completed",
}


def as_api_token(client, scopes=("agent-config:read", "call-log:write")):
    client.app.dependency_overrides[get_introspection] = lambda: IntrospectResult(
        active=True, token_type="api_token", scopes=list(scopes), token_id="tok-1"
    )


async def _agent(client, org="org-1"):
    set_auth(client.app, "u1", org)
    return data(await client.post("/api/v1/agents", json={"name": "Sona"}))["id"]


async def test_runtime_posts_a_call_log_and_it_is_stored_with_the_full_payload(client):
    agent_id = await _agent(client)
    as_api_token(client)
    body = {"agent_id": agent_id, "call_payload": {"interaction": INTERACTION}}
    res = await client.post("/api/v1/call-logs", json=body)
    assert code(res) == 201 and data(res)["created"] is True

    doc = await CallLog.find_one(CallLog.agent_id == agent_id)
    assert doc.org_id == "org-1" and doc.session_id == "RM_d3VNiPifoFwV"
    assert (doc.source, doc.direction, doc.status, doc.test) == ("website", "inbound", "completed", True)
    assert doc.duration == "0:24" and doc.duration_seconds == 24 and doc.messages == 2
    assert doc.hangup_reason == "client_initiated_disconnect"
    assert doc.started_at.isoformat().startswith("2026-10-29T07:02:03")  # from the journey's epoch, not the zone-less string
    assert doc.interaction == INTERACTION  # stored exactly as received

    # A retry for the same session updates in place.
    again = await client.post("/api/v1/call-logs", json={**body, "call_payload": {"interaction": {**INTERACTION, "status": "failed"}}})
    assert code(again) == 200 and data(again)["created"] is False and data(again)["id"] == data(res)["id"]
    assert await CallLog.find(CallLog.agent_id == agent_id).count() == 1
    assert (await CallLog.find_one(CallLog.agent_id == agent_id)).status == "failed"


async def test_only_an_api_token_with_the_scope_may_post_and_the_payload_is_validated(client):
    agent_id = await _agent(client)
    body = {"agent_id": agent_id, "call_payload": {"interaction": INTERACTION}}
    set_auth(client.app, "u1", "org-1")  # a user token
    assert error_type(await client.post("/api/v1/call-logs", json=body)) == "UNAUTHORIZED"
    as_api_token(client, scopes=("agent-config:read",))
    assert error_type(await client.post("/api/v1/call-logs", json=body)) == "FORBIDDEN"
    as_api_token(client)
    assert error_type(await client.post("/api/v1/call-logs", json={**body, "agent_id": "6ae2fcd6bc254d03a880f339"})) == "NOT_FOUND"
    assert error_type(await client.post("/api/v1/call-logs", json={**body, "agent_id": "nope"})) == "NOT_FOUND"
    assert error_type(await client.post("/api/v1/call-logs", json={"agent_id": agent_id, "call_payload": {}})) == "UNPROCESSABLE_ENTITY"
    assert await CallLog.find().count() == 0


async def test_org_users_read_their_agents_logs_only(client):
    agent_id = await _agent(client)
    as_api_token(client)
    for n, (status, test) in enumerate([("completed", True), ("missed", False)]):
        inter = {**INTERACTION, "status": status, "test": test, "details": {**INTERACTION["details"], "session_id": f"S{n}", "from_phone": f"+9198765000{n}"}}
        await client.post("/api/v1/call-logs", json={"agent_id": agent_id, "call_payload": {"interaction": inter}})

    set_auth(client.app, "u1", "org-1")
    base = f"/api/v1/agents/{agent_id}/call-logs"
    listing = data(await client.get(base))
    assert listing["total"] == 2 and "interaction" not in listing["items"][0]
    assert data(await client.get(base, params={"status": "missed"}))["total"] == 1
    assert data(await client.get(base, params={"test": "true"}))["items"][0]["session_id"] == "S0"
    assert data(await client.get(base, params={"q": "98765000"}))["total"] == 2
    one = data(await client.get(f"{base}/{listing['items'][0]['id']}"))
    assert one["interaction"]["interaction_journey"][1]["role"] == "assistant"
    assert one["interaction"]["token_usage"]["llm_input_token"] == 742

    # QA can view; another organization sees nothing (404, not 403); unknown ids are 404.
    set_auth(client.app, "qa", "org-1", role=Role.QA)
    assert data(await client.get(base))["total"] == 2
    set_auth(client.app, "u2", "org-2")
    assert error_type(await client.get(base)) == "NOT_FOUND"
    assert error_type(await client.get(f"{base}/{listing['items'][0]['id']}")) == "NOT_FOUND"
    set_auth(client.app, "u1", "org-1")
    assert error_type(await client.get(f"{base}/6ae2fcd6bc254d03a880f339")) == "NOT_FOUND"

    # Voice access can be switched off per organization; deleting the agent deletes its logs.
    set_auth(client.app, "u1", "org-1", features=["whatsapp"])
    assert error_type(await client.get(base)) == "FORBIDDEN"
    set_auth(client.app, "u1", "org-1")
    await client.delete(f"/api/v1/agents/{agent_id}")
    assert await CallLog.find(CallLog.agent_id == agent_id).count() == 0
