import pytest
from common.enums import Role

from tests.factories import auth_header, code, data, make_org, make_user
from users_service.core.config import get_settings

pytestmark = pytest.mark.asyncio


def _internal():
    return {"X-Internal-Api-Key": get_settings().internal_api_key}


async def _introspect(client, token):
    resp = await client.post("/api/v1/internal/introspect", headers=_internal(), json={"access_token": token})
    return data(resp)


async def test_super_admin_creates_lists_and_revokes(client):
    admin = await make_user(None, Role.SUPER_ADMIN, "tok-super@example.com")
    h = auth_header(admin)

    created = await client.post("/api/v1/api-tokens", headers=h, json={"name": "voice-agent"})
    assert code(created) == 201
    body = data(created)
    token = body["token"]
    assert token.startswith("bt_") and body["scopes"] == ["agent-config:read"]

    listed = data(await client.get("/api/v1/api-tokens", headers=h))
    assert [t["id"] for t in listed] == [body["id"]]
    assert "token" not in listed[0] and listed[0]["token_prefix"] == token[:10]

    live = await _introspect(client, token)
    assert live["active"] is True and live["token_type"] == "api_token" and live["scopes"] == ["agent-config:read"]

    revoked = await client.delete(f"/api/v1/api-tokens/{body['id']}", headers=h)
    assert code(revoked) == 200 and data(revoked)["revoked"] is True
    assert (await _introspect(client, token))["active"] is False


async def test_only_super_admin_can_manage_tokens(client):
    org = await make_org("Org", "org-tok")
    for role, email in ((Role.ADMIN, "tok-admin@example.com"), (Role.QA, "tok-qa@example.com")):
        user = await make_user(org.id, role, email)
        h = auth_header(user)
        assert code(await client.post("/api/v1/api-tokens", headers=h, json={"name": "x"})) == 403
        assert code(await client.get("/api/v1/api-tokens", headers=h)) == 403
        assert code(await client.delete("/api/v1/api-tokens/000000000000000000000000", headers=h)) == 403


async def test_unknown_or_forged_tokens_are_inactive(client):
    assert (await _introspect(client, "bt_not-a-real-token"))["active"] is False
    admin = await make_user(None, Role.SUPER_ADMIN, "tok-super2@example.com")
    assert code(await client.delete("/api/v1/api-tokens/000000000000000000000000", headers=auth_header(admin))) == 404
