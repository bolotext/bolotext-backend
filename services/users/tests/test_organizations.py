import pytest
from beanie import PydanticObjectId

from common.enums import Role
from tests.factories import auth_header, code, data, error_type, make_org, make_user

pytestmark = pytest.mark.asyncio


async def test_super_admin_creates_org_with_bootstrap_admin(client):
    super_admin = await make_user(None, Role.SUPER_ADMIN, "super-org@example.com")

    resp = await client.post(
        "/api/v1/organizations",
        headers=auth_header(super_admin),
        json={
            "name": "Acme Corp",
            "slug": "acme-corp",
            "admin_email": "admin@acme.example.com",
            "admin_full_name": "Acme Admin",
        },
    )
    assert resp.status_code == 200
    assert code(resp) == 201
    body = data(resp)
    assert body["organization"]["slug"] == "acme-corp"
    assert body["admin_user_id"]

    login_resp = await client.post(
        "/api/v1/auth/login", json={"credential": "admin@acme.example.com"}
    )
    assert login_resp.status_code == 200


async def test_duplicate_slug_is_rejected(client):
    super_admin = await make_user(None, Role.SUPER_ADMIN, "super-org2@example.com")

    payload = {"name": "Beta Inc", "slug": "beta-inc"}
    first = await client.post("/api/v1/organizations", headers=auth_header(super_admin), json=payload)
    assert first.status_code == 200
    assert code(first) == 201

    second = await client.post("/api/v1/organizations", headers=auth_header(super_admin), json=payload)
    assert second.status_code == 200
    assert code(second) == 409
    assert error_type(second) == "CONFLICT"


async def test_non_super_admin_cannot_create_org(client):
    org = await make_org("Delta LLC", "delta-llc")
    org_admin = await make_user(org.id, Role.ADMIN, "not-super@example.com")
    resp = await client.post(
        "/api/v1/organizations",
        headers=auth_header(org_admin),
        json={"name": "Gamma", "slug": "gamma"},
    )
    assert resp.status_code == 200
    assert code(resp) == 403


async def test_org_features_are_set_on_create_updated_later_and_introspected(client):
    from users_service.core.config import get_settings

    super_admin = await make_user(None, Role.SUPER_ADMIN, "feat-super@example.com")
    h = auth_header(super_admin)

    # Defaults to every product area; a Super Admin can restrict it at creation.
    full = await client.post("/api/v1/organizations", headers=h, json={"name": "Full", "slug": "full-org"})
    assert data(full)["organization"]["features"] == ["voice_agents", "whatsapp", "sms"]
    created = await client.post(
        "/api/v1/organizations", headers=h, json={"name": "Msg Only", "slug": "msg-only", "features": ["whatsapp", "sms"]}
    )
    org = data(created)["organization"]
    assert org["features"] == ["whatsapp", "sms"]
    for bad in ([], ["telegram"]):
        r = await client.post("/api/v1/organizations", headers=h, json={"name": "X", "slug": "x-org", "features": bad})
        assert error_type(r) == "VALIDATION_ERROR"

    member = await make_user(PydanticObjectId(org["id"]), Role.ADMIN, "feat-admin@example.com")
    mh = auth_header(member)

    async def introspect():
        token = mh["Authorization"].split()[1]
        r = await client.post(
            "/api/v1/internal/introspect",
            headers={"X-Internal-Api-Key": get_settings().internal_api_key},
            json={"access_token": token},
        )
        return data(r)

    assert (await introspect())["features"] == ["whatsapp", "sms"]
    assert data(await client.get("/api/v1/users/me", headers=mh))["features"] == ["whatsapp", "sms"]
    assert set(data(await client.get("/api/v1/users/me", headers=h))["features"]) == {"voice_agents", "whatsapp", "sms"}

    # Updating takes effect immediately; an empty list is refused; org users can't change it.
    upd = await client.patch(f"/api/v1/organizations/{org['id']}", headers=h, json={"features": ["voice_agents"]})
    assert data(upd)["features"] == ["voice_agents"]
    assert (await introspect())["features"] == ["voice_agents"]
    assert error_type(await client.patch(f"/api/v1/organizations/{org['id']}", headers=h, json={"features": []})) == "VALIDATION_ERROR"
    assert error_type(await client.patch(f"/api/v1/organizations/{org['id']}", headers=mh, json={"features": ["sms"]})) == "FORBIDDEN"
