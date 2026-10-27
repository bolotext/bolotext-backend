import pytest

from common.enums import Role
from tests.factories import auth_header, code, data, make_org, make_user

pytestmark = pytest.mark.asyncio


async def test_admin_cannot_see_other_org_users(client):
    org_a = await make_org("Org A", "org-a")
    org_b = await make_org("Org B", "org-b")
    admin_a = await make_user(org_a.id, Role.ADMIN, "admin-a@example.com")
    dev_b = await make_user(org_b.id, Role.DEVELOPER, "dev-b@example.com")

    list_resp = await client.get("/api/v1/users", headers=auth_header(admin_a))
    assert list_resp.status_code == 200
    assert code(list_resp) == 200
    emails = {u["email"] for u in data(list_resp)}
    assert emails == {"admin-a@example.com"}

    get_resp = await client.get(f"/api/v1/users/{dev_b.id}", headers=auth_header(admin_a))
    assert get_resp.status_code == 200
    assert code(get_resp) == 404


async def test_admin_cannot_access_organizations_endpoint(client):
    org = await make_org("Org H", "org-h")
    admin = await make_user(org.id, Role.ADMIN, "admin-h@example.com")
    resp = await client.get("/api/v1/organizations", headers=auth_header(admin))
    assert resp.status_code == 200
    assert code(resp) == 403


async def test_qa_cannot_list_or_get_users(client):
    org = await make_org("Org C", "org-c")
    qa = await make_user(org.id, Role.QA, "qa@example.com")
    other = await make_user(org.id, Role.DEVELOPER, "dev-c@example.com")

    list_resp = await client.get("/api/v1/users", headers=auth_header(qa))
    assert list_resp.status_code == 200
    assert code(list_resp) == 403

    get_resp = await client.get(f"/api/v1/users/{other.id}", headers=auth_header(qa))
    assert get_resp.status_code == 200
    assert code(get_resp) == 403

    me_resp = await client.get("/api/v1/users/me", headers=auth_header(qa))
    assert me_resp.status_code == 200
    assert code(me_resp) == 200
    assert data(me_resp)["email"] == "qa@example.com"


async def test_developer_has_read_only_access(client):
    org = await make_org("Org D", "org-d")
    dev = await make_user(org.id, Role.DEVELOPER, "dev@example.com")

    list_resp = await client.get("/api/v1/users", headers=auth_header(dev))
    assert list_resp.status_code == 200
    assert code(list_resp) == 200

    create_resp = await client.post(
        "/api/v1/users",
        headers=auth_header(dev),
        json={"email": "new@example.com", "full_name": "New", "role": "QA"},
    )
    assert create_resp.status_code == 200
    assert code(create_resp) == 403

    patch_resp = await client.patch(
        f"/api/v1/users/{dev.id}", headers=auth_header(dev), json={"full_name": "Renamed"}
    )
    assert patch_resp.status_code == 200
    assert code(patch_resp) == 403


async def test_admin_can_create_and_disable_user_in_own_org(client):
    org = await make_org("Org E", "org-e")
    admin = await make_user(org.id, Role.ADMIN, "admin-e@example.com")

    create_resp = await client.post(
        "/api/v1/users",
        headers=auth_header(admin),
        json={"email": "dev-e@example.com", "full_name": "Dev E", "role": "DEVELOPER"},
    )
    assert create_resp.status_code == 200
    assert code(create_resp) == 201
    created = data(create_resp)
    assert created["organization_id"] == str(org.id)

    disable_resp = await client.delete(f"/api/v1/users/{created['id']}", headers=auth_header(admin))
    assert disable_resp.status_code == 200
    assert code(disable_resp) == 200
    assert data(disable_resp)["status"] == "disabled"


async def test_admin_cannot_create_user_in_another_org(client):
    org_a = await make_org("Org I", "org-i")
    org_b = await make_org("Org J", "org-j")
    admin_a = await make_user(org_a.id, Role.ADMIN, "admin-i@example.com")

    create_resp = await client.post(
        "/api/v1/users",
        headers=auth_header(admin_a),
        json={
            "email": "sneaky@example.com",
            "full_name": "Sneaky",
            "role": "DEVELOPER",
            "organization_id": str(org_b.id),
        },
    )
    assert create_resp.status_code == 200
    assert code(create_resp) == 201
    # organization_id from the client is ignored for org-scoped callers; it lands in the caller's own org.
    assert data(create_resp)["organization_id"] == str(org_a.id)


async def test_role_escalation_to_super_admin_is_rejected(client):
    org = await make_org("Org F", "org-f")
    admin = await make_user(org.id, Role.ADMIN, "admin-f@example.com")
    resp = await client.post(
        "/api/v1/users",
        headers=auth_header(admin),
        json={"email": "x@example.com", "full_name": "X", "role": "SUPER_ADMIN"},
    )
    assert resp.status_code == 200
    assert code(resp) == 400


async def test_super_admin_can_manage_across_orgs(client):
    org_a = await make_org("Org G", "org-g")
    super_admin = await make_user(None, Role.SUPER_ADMIN, "super-g@example.com")

    create_resp = await client.post(
        "/api/v1/users",
        headers=auth_header(super_admin),
        json={
            "email": "admin-g@example.com",
            "full_name": "Admin G",
            "role": "ADMIN",
            "organization_id": str(org_a.id),
        },
    )
    assert create_resp.status_code == 200
    assert code(create_resp) == 201
    assert data(create_resp)["organization_id"] == str(org_a.id)

    list_resp = await client.get("/api/v1/organizations", headers=auth_header(super_admin))
    assert list_resp.status_code == 200
    assert code(list_resp) == 200
    assert any(o["slug"] == "org-g" for o in data(list_resp))


async def test_self_profile_update_only_changes_name(client):
    org = await make_org("Org K", "org-k")
    dev = await make_user(org.id, Role.DEVELOPER, "dev-k@example.com")

    resp = await client.patch("/api/v1/users/me", headers=auth_header(dev), json={"full_name": "Dev K"})
    assert code(resp) == 200
    body = data(resp)
    assert body["full_name"] == "Dev K"
    assert "must_change_password" not in body
    assert "hashed_password" not in body

