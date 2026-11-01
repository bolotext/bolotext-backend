import base64
import hashlib
import hmac
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


# scrypt (stdlib) for password hashing: memory-hard, no extra dependency.
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N, _SCRYPT_R, _SCRYPT_P, base64.b64encode(salt).decode(), base64.b64encode(digest).decode()
    )


def verify_password(password: str, hashed: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = hashed.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest_b64)
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=base64.b64decode(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected)


# Verified against when no usable account/password exists, so response time
# doesn't reveal whether an email is registered.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(16))
