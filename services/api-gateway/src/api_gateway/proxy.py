"""Minimal reverse proxy: forwards a request to an upstream microservice and
relays its response back verbatim. Downstream services still do their own JWT
verification and RBAC (see users_service.core.deps) — the gateway does not
inspect or terminate auth today, it only routes. Centralizing auth here is a
reasonable next step once there's a second real backend to justify it.
"""

import httpx
from common.errors import BadGatewayError
from fastapi import Request, Response

from api_gateway.config import get_settings

PUBLIC_BASE_URL_HEADER = "X-Public-Base-Url"

# Hop-by-hop headers must not be forwarded (RFC 7230 §6.1).
_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


def _filter_headers(headers: httpx.Headers | dict) -> dict:
    return {k: v for k, v in headers.items() if k.lower() not in _HOP_BY_HOP_HEADERS}


def public_base_url(request: Request) -> str:
    """The URL clients (and e.g. Twilio) use to reach this gateway: the pinned
    `PUBLIC_URL` if set, else the forwarded/Host header of this request.
    """
    pinned = get_settings().public_url
    if pinned:
        return pinned.rstrip("/")
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
    host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc)).split(",")[0].strip()
    return f"{scheme}://{host}"


async def forward(client: httpx.AsyncClient, request: Request, upstream_base: str, upstream_path: str) -> Response:
    url = f"{upstream_base.rstrip('/')}/{upstream_path.lstrip('/')}"
    body = await request.body()

    try:
        upstream_response = await client.request(
            method=request.method,
            url=url,
            params=request.query_params,
            # Set by the gateway itself, so a client-supplied value is never trusted.
            headers={**_filter_headers(request.headers), PUBLIC_BASE_URL_HEADER: public_base_url(request)},
            content=body,
        )
    except httpx.RequestError as exc:
        raise BadGatewayError(f"Upstream service is unreachable: {exc}") from exc

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=_filter_headers(upstream_response.headers),
    )
