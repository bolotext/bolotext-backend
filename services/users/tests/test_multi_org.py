import pytest

from common.enums import Role

from users_service.memberships.model import OrganizationMembership
from tests.factories import auth_header, code, data, make_org, make_user

pytestmark = pytest.mark.asyncio


async def test_single_membership_login_auto_selects_org(client):
    org = await make_org("Org Single", "org-single")
    await make_user(org.id, Role.ADMIN, "single@example.com", password="password123")

    resp = await client.post("/api/v1/auth/login", json={"email": "single@example.com", "password": "password123"})
    assert resp.status_code == 200
    body = data(resp)
    assert body["access_token"]
    assert body["organizations"] is None


async def test_multi_membership_login_requires_selection(client):
    org_a = await make_org("Org Multi A", "org-multi-a")
    org_b = await make_org("Org Multi B", "org-multi-b")
    user = await make_user(org_a.id, Role.ADMIN, "multi@example.com", password="password123")
    await OrganizationMembership(user_id=user.id, organization_id=org_b.id, role=Role.QA).insert()

    resp = await client.post("/api/v1/auth/login", json={"email": "multi@example.com", "password": "password123"})
    assert resp.status_code == 200
    body = data(resp)
    assert body["access_token"] is None
    assert body["refresh_token"] is None
    orgs = {o["organization_id"]: o["role"] for o in body["organizations"]}
    assert orgs == {str(org_a.id): "ADMIN", str(org_b.id): "QA"}

    resp2 = await client.post(
        "/api/v1/auth/login",
        json={"email": "multi@example.com", "password": "password123", "organization_id": str(org_b.id)},
    )
    assert resp2.status_code == 200
    body2 = data(resp2)
    assert body2["access_token"]

    me_resp = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {body2['access_token']}"})
    assert code(me_resp) == 200
    assert data(me_resp)["role"] == "QA"
    assert data(me_resp)["organization_id"] == str(org_b.id)


async def test_switch_organization_reissues_token_for_different_role(client):
    org_a = await make_org("Org Switch A", "org-switch-a")
    org_b = await make_org("Org Switch B", "org-switch-b")
    user = await make_user(org_a.id, Role.ADMIN, "switch@example.com", password="password123")
    await OrganizationMembership(user_id=user.id, organization_id=org_b.id, role=Role.DEVELOPER).insert()

    resp = await client.post(
        "/api/v1/auth/switch-organization", headers=auth_header(user, org_a.id), json={"organization_id": str(org_b.id)}
    )
    assert resp.status_code == 200
    switched = data(resp)
    assert switched["access_token"]

    me_resp = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {switched['access_token']}"})
    assert data(me_resp)["role"] == "DEVELOPER"
    assert data(me_resp)["organization_id"] == str(org_b.id)


async def test_switch_organization_rejected_without_membership(client):
    org_a = await make_org("Org NoAccess A", "org-noaccess-a")
    org_b = await make_org("Org NoAccess B", "org-noaccess-b")
    user = await make_user(org_a.id, Role.ADMIN, "noaccess@example.com", password="password123")

    resp = await client.post(
        "/api/v1/auth/switch-organization", headers=auth_header(user, org_a.id), json={"organization_id": str(org_b.id)}
    )
    assert resp.status_code == 200
    assert code(resp) == 403


async def test_refresh_reissues_access_token_for_pinned_org(client):
    org = await make_org("Org Refresh", "org-refresh")
    await make_user(org.id, Role.DEVELOPER, "refresh-org@example.com", password="password123")

    login_resp = await client.post(
        "/api/v1/auth/login", json={"email": "refresh-org@example.com", "password": "password123"}
    )
    refresh_token = data(login_resp)["refresh_token"]

    refresh_resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert code(refresh_resp) == 200
    new_access = data(refresh_resp)["access_token"]

    me_resp = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {new_access}"})
    assert data(me_resp)["role"] == "DEVELOPER"
    assert data(me_resp)["organization_id"] == str(org.id)


async def test_removed_membership_is_rejected_immediately(client):
    org = await make_org("Org Revoke", "org-revoke")
    user = await make_user(org.id, Role.QA, "revoke@example.com", password="password123")
    membership = await OrganizationMembership.find_one(
        OrganizationMembership.user_id == user.id, OrganizationMembership.organization_id == org.id
    )
    headers = auth_header(user, org.id)
    await membership.delete()

    resp = await client.get("/api/v1/users/me", headers=headers)
    assert resp.status_code == 200
    assert code(resp) == 401


async def test_super_admin_login_ignores_organization_id(client):
    super_admin = await make_user(None, Role.SUPER_ADMIN, "super-multi@example.com", password="password123")
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "super-multi@example.com", "password": "password123"}
    )
    assert resp.status_code == 200
    body = data(resp)
    assert body["access_token"]
    assert body["organizations"] is None
