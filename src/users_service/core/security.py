import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from common.jwt import ACCESS_TOKEN_TYPE, REFRESH_TOKEN_TYPE, decode_token  # noqa: F401 (re-exported)

from users_service.core.config import get_settings

settings = get_settings()


def _create_token(subject: str, token_type: str, expires_delta: timedelta, extra_claims: dict[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        **extra_claims,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str, organization_id: str | None) -> str:
    """Role is deliberately not a claim here — it's per-organization
    membership now, so it's resolved fresh on every request instead of
    trusted from the token. See users_service.core.deps.get_current_auth.
    """
    return _create_token(
        subject=user_id,
        token_type=ACCESS_TOKEN_TYPE,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        extra_claims={"organization_id": organization_id},
    )


def create_refresh_token(user_id: str) -> str:
    return _create_token(
        subject=user_id,
        token_type=REFRESH_TOKEN_TYPE,
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
        extra_claims={"jti": secrets.token_urlsafe(16)},
    )


def decode_own_token(token: str) -> dict[str, Any]:
    """Decode a token using this service's own configured secret/algorithm."""
    return decode_token(token, settings.jwt_secret, settings.jwt_algorithm)


def hash_refresh_token(token: str) -> str:
    """Refresh tokens are stored hashed so a DB read never yields a usable token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
