"""Encryption at rest for the stored Twilio auth token (Fernet / AES-128-CBC + HMAC)."""

import base64
import hashlib
from functools import lru_cache

from common.log_utils import setup_logger
from cryptography.fernet import Fernet, InvalidToken

from agents_service.core.config import get_settings

logger = setup_logger(__name__)


@lru_cache
def _fernet() -> Fernet:
    settings = get_settings()
    if settings.whatsapp_encryption_key:
        return Fernet(settings.whatsapp_encryption_key.encode())
    logger.warning("WHATSAPP_ENCRYPTION_KEY is not set; deriving the token-encryption key from INTERNAL_API_KEY")
    digest = hashlib.sha256(f"whatsapp-settings:{settings.internal_api_key}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    """Raises ValueError if the token can't be decrypted (e.g. the key changed)."""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise ValueError("stored value can't be decrypted with the current encryption key") from e
