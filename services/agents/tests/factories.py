from common.enums import Role

from agents_service.core.deps import AuthContext, get_current_auth, get_introspection
from agents_service.core.http_client import IntrospectResult


def set_auth(
    app, user_id: str, org_id: str | None, role: Role = Role.ADMIN, features: list[str] | None = None
) -> None:
    """Overrides the introspection-based auth dependency for tests, so the
    suite never needs a real Users service to call out to.
    """
    app.dependency_overrides[get_current_auth] = lambda: AuthContext(
        user_id=user_id, organization_id=org_id, role=role,
        features=None if features is None else frozenset(features),
    )
    # Routes that also accept API tokens (get_config_auth) resolve identity from
    # the introspection result rather than get_current_auth.
    app.dependency_overrides[get_introspection] = lambda: IntrospectResult(
        active=True, user_id=user_id, organization_id=org_id, role=str(role), features=features
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
