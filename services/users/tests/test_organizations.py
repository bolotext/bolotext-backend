import pytest

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
            "admin_password": "password123",
            "admin_full_name": "Acme Admin",
        },
    )
    assert resp.status_code == 200
    assert code(resp) == 201
    body = data(resp)
    assert body["organization"]["slug"] == "acme-corp"
    assert body["admin_user_id"]

    login_resp = await client.post(
        "/api/v1/auth/login", json={"email": "admin@acme.example.com", "password": "password123"}
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
