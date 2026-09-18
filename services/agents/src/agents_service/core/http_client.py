"""Client for the Users service's internal token-introspection endpoint.
Identity for this service is always resolved this way rather than decoding
JWTs locally (see agents_service.core.deps) — see the platform README and the
original stub's file header for why.
"""

import httpx
from common.errors import BadGatewayError
from pydantic import BaseModel

from agents_service.core.config import get_settings

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = httpx.AsyncClient(
            base_url=settings.users_service_url, timeout=settings.introspect_timeout_seconds
        )
    return _client


async def close_http_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


class IntrospectResult(BaseModel):
    active: bool
    user_id: str | None = None
    organization_id: str | None = None
    role: str | None = None


async def introspect(access_token: str) -> IntrospectResult:
    settings = get_settings()
    client = _get_client()
    try:
        response = await client.post(
            "/api/v1/internal/introspect",
            json={"access_token": access_token},
            headers={"X-Internal-Api-Key": settings.internal_api_key},
        )
    except httpx.RequestError as exc:
        raise BadGatewayError(f"Users service is unreachable: {exc}") from exc

    body = response.json()
    if body.get("status") != "success" or body.get("data") is None:
        return IntrospectResult(active=False)
    return IntrospectResult(**body["data"])
