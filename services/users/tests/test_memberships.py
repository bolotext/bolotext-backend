import pytest

from common.enums import Role

from tests.factories import auth_header, code, data, make_org, make_user

pytestmark = pytest.mark.asyncio


async def test_admin_adds_existing_user_to_own_org(client):
    org_a = await make_org("Org Mem A", "org-mem-a")
    org_b = await make_org("Org Mem B", "org-mem-b")
    admin_a = await make_user(org_a.id, Role.ADMIN, "admin-mem-a@example.com")
    dev_b = await make_user(org_b.id, Role.DEVELOPER, "dev-mem-b@example.com")

    resp = await client.post(
        f"/api/v1/organizations/{org_a.id}/members",
        headers=auth_header(admin_a),
        json={"user_id": str(dev_b.id), "role": "QA"},
    )
    assert resp.status_code == 200
    assert code(resp) == 201
    body = data(resp)
    assert body["role"] == "QA"
    assert body["organization_id"] == str(org_a.id)

    # dev_b now has two memberships with two different roles.
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"credential": "dev-mem-b@example.com", "organization_id": str(org_a.id)},
    )
    assert code(login_resp) == 200
    access_token = data(login_resp)["access_token"]
    me_resp = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {access_token}"})
    assert data(me_resp)["role"] == "QA"


async def test_admin_cannot_add_member_to_another_org(client):
    org_a = await make_org("Org Mem C", "org-mem-c")
    org_b = await make_org("Org Mem D", "org-mem-d")
    admin_a = await make_user(org_a.id, Role.ADMIN, "admin-mem-c@example.com")
    dev_b = await make_user(org_b.id, Role.DEVELOPER, "dev-mem-d@example.com")

    resp = await client.post(
        f"/api/v1/organizations/{org_b.id}/members",
        headers=auth_header(admin_a),
        json={"user_id": str(dev_b.id), "role": "QA"},
    )
    assert resp.status_code == 200
    assert code(resp) == 403


async def test_duplicate_membership_is_rejected(client):
    org = await make_org("Org Mem E", "org-mem-e")
    admin = await make_user(org.id, Role.ADMIN, "admin-mem-e@example.com")
    dev = await make_user(org.id, Role.DEVELOPER, "dev-mem-e@example.com")

    resp = await client.post(
        f"/api/v1/organizations/{org.id}/members",
        headers=auth_header(admin),
        json={"user_id": str(dev.id), "role": "QA"},
    )
    assert resp.status_code == 200
    assert code(resp) == 409


async def test_admin_updates_and_removes_member_role(client):
    org = await make_org("Org Mem F", "org-mem-f")
    admin = await make_user(org.id, Role.ADMIN, "admin-mem-f@example.com")
    dev = await make_user(org.id, Role.DEVELOPER, "dev-mem-f@example.com")

    update_resp = await client.patch(
        f"/api/v1/organizations/{org.id}/members/{dev.id}", headers=auth_header(admin), json={"role": "QA"}
    )
    assert code(update_resp) == 200
    assert data(update_resp)["role"] == "QA"

    list_resp = await client.get(f"/api/v1/organizations/{org.id}/members", headers=auth_header(admin))
    assert code(list_resp) == 200
    roles = {m["email"]: m["role"] for m in data(list_resp)}
    assert roles["dev-mem-f@example.com"] == "QA"

    remove_resp = await client.delete(f"/api/v1/organizations/{org.id}/members/{dev.id}", headers=auth_header(admin))
    assert code(remove_resp) == 200

    login_resp = await client.post(
        "/api/v1/auth/login", json={"credential": "dev-mem-f@example.com"}
    )
    assert code(login_resp) == 401


async def test_developer_cannot_manage_members(client):
    org = await make_org("Org Mem G", "org-mem-g")
    dev = await make_user(org.id, Role.DEVELOPER, "dev-mem-g@example.com")
    other = await make_user(org.id, Role.QA, "qa-mem-g@example.com")

    resp = await client.post(
        f"/api/v1/organizations/{org.id}/members",
        headers=auth_header(dev),
        json={"user_id": str(other.id), "role": "ADMIN"},
    )
    assert resp.status_code == 200
    assert code(resp) == 403


async def test_super_admin_manages_members_across_orgs(client):
    org = await make_org("Org Mem H", "org-mem-h")
    super_admin = await make_user(None, Role.SUPER_ADMIN, "super-mem-h@example.com")
    dev = await make_user(org.id, Role.DEVELOPER, "dev-mem-h@example.com")

    list_resp = await client.get(f"/api/v1/organizations/{org.id}/members", headers=auth_header(super_admin))
    assert code(list_resp) == 200
    assert any(m["email"] == "dev-mem-h@example.com" for m in data(list_resp))


async def test_get_my_organizations(client):
    org_a = await make_org("Org Mine A", "org-mine-a")
    org_b = await make_org("Org Mine B", "org-mine-b")
    admin_a = await make_user(org_a.id, Role.ADMIN, "mine@example.com")

    resp = await client.post(
        f"/api/v1/organizations/{org_b.id}/members",
        headers=auth_header(await make_user(org_b.id, Role.ADMIN, "admin-mine-b@example.com")),
        json={"user_id": str(admin_a.id), "role": "DEVELOPER"},
    )
    assert code(resp) == 201

    my_orgs_resp = await client.get("/api/v1/users/me/organizations", headers=auth_header(admin_a, org_a.id))
    assert code(my_orgs_resp) == 200
    by_org = {o["organization_id"]: o["role"] for o in data(my_orgs_resp)}
    assert by_org == {str(org_a.id): "ADMIN", str(org_b.id): "DEVELOPER"}


async def test_create_user_with_existing_email_adds_membership_in_other_org(client):
    org_a = await make_org("Org A2", "org-a2")
    org_b = await make_org("Org B2", "org-b2")
    admin_b = await make_user(org_b.id, Role.ADMIN, "admin-b2@example.com")
    await make_user(org_a.id, Role.DEVELOPER, "shared@example.com")

    resp = await client.post(
        "/api/v1/users",
        headers=auth_header(admin_b),
        json={"email": "shared@example.com", "full_name": "Shared", "role": "QA"},
    )
    assert code(resp) == 201
    assert data(resp)["organization_id"] == str(org_b.id)
    assert data(resp)["role"] == "QA"

    again = await client.post(
        "/api/v1/users",
        headers=auth_header(admin_b),
        json={"email": "shared@example.com", "full_name": "Shared", "role": "QA"},
    )
    assert code(again) == 409
