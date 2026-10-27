import pytest

from common.enums import Role

from users_service.enums import UserStatus
from tests.factories import code, data, error_type, make_user

pytestmark = pytest.mark.asyncio


async def test_login_success(client):
    await make_user(None, Role.SUPER_ADMIN, "super@example.com")
    resp = await client.post("/api/v1/auth/login", json={"credential": "super@example.com"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    body = data(resp)
    assert body["access_token"]
    assert body["refresh_token"]


async def test_login_invalid_google_credential(client):
    await make_user(None, Role.SUPER_ADMIN, "super2@example.com")
    resp = await client.post("/api/v1/auth/login", json={"credential": "invalid"})
    assert resp.status_code == 200
    assert code(resp) == 401
    assert resp.json()["status"] == "error"
    assert error_type(resp) == "UNAUTHORIZED"


async def test_login_unknown_email(client):
    resp = await client.post("/api/v1/auth/login", json={"credential": "nobody@example.com"})
    assert resp.status_code == 200
    assert code(resp) == 401


async def test_login_disabled_account(client):
    await make_user(None, Role.SUPER_ADMIN, "super3@example.com", status=UserStatus.DISABLED)
    resp = await client.post("/api/v1/auth/login", json={"credential": "super3@example.com"})
    assert resp.status_code == 200
    assert code(resp) == 401


async def test_refresh_then_logout_revokes_token(client):
    await make_user(None, Role.SUPER_ADMIN, "super4@example.com")
    login_resp = await client.post(
        "/api/v1/auth/login", json={"credential": "super4@example.com"}
    )
    refresh_token = data(login_resp)["refresh_token"]

    refresh_resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_resp.status_code == 200
    assert data(refresh_resp)["access_token"]

    logout_resp = await client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    assert logout_resp.status_code == 200
    assert logout_resp.json()["status"] == "success"

    refresh_after_logout = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_after_logout.status_code == 200
    assert code(refresh_after_logout) == 401


async def test_unauthenticated_request_rejected(client):
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 200
    assert code(resp) == 401
