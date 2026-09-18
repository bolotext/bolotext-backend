from common.enums import Role

from agents_service.core.deps import AuthContext, get_current_auth


def set_auth(app, user_id: str, org_id: str | None, role: Role = Role.ADMIN) -> None:
    """Overrides the introspection-based auth dependency for tests, so the
    suite never needs a real Users service to call out to.
    """
    app.dependency_overrides[get_current_auth] = lambda: AuthContext(
        user_id=user_id, organization_id=org_id, role=role
    )


def data(resp) -> dict:
    """Unwrap the {status, code, message, data} success envelope."""
    return resp.json()["data"]


def code(resp) -> int:
    """The envelope's real status code. The HTTP transport status is always
    200 — see common.errors.register_exception_handlers.
    """
    return resp.json()["code"]


def error_type(resp) -> str:
    """Unwrap the {status, code, message, errors: {type, ...}} error envelope."""
    return resp.json()["errors"]["type"]
