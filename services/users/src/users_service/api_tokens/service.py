import hashlib
import secrets

from beanie import PydanticObjectId
from common.errors import NotFoundError

from users_service.api_tokens import repository as repo
from users_service.api_tokens.model import ApiToken
from users_service.api_tokens.schema import AGENT_CONFIG_READ, ApiTokenCreated, ApiTokenOut

# Every API token starts with this, so the introspect endpoint can tell one
# apart from a user JWT without trying to decode it.
TOKEN_PREFIX = "bt_"


def hash_token(token: str) -> str:
    """Tokens are 256 bits of randomness, so a plain SHA-256 is sufficient
    (there is nothing to brute-force, unlike a human-chosen password)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def to_out(record: ApiToken) -> ApiTokenOut:
    return ApiTokenOut(
        id=str(record.id),
        name=record.name,
        token_prefix=record.token_prefix,
        scopes=record.scopes,
        created_by=str(record.created_by),
        created_at=record.created_at,
        revoked=record.revoked,
        revoked_at=record.revoked_at,
    )


async def create_token(name: str, created_by: PydanticObjectId) -> ApiTokenCreated:
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    record = await repo.create(
        name=name.strip(),
        token_prefix=token[:10],
        token_hash=hash_token(token),
        scopes=[AGENT_CONFIG_READ],
        created_by=created_by,
    )
    return ApiTokenCreated(**to_out(record).model_dump(), token=token)


async def list_tokens() -> list[ApiTokenOut]:
    return [to_out(r) for r in await repo.list_all()]


async def revoke_token(token_id: str, revoked_by: PydanticObjectId) -> ApiTokenOut:
    try:
        record = await repo.get(PydanticObjectId(token_id))
    except Exception:
        record = None
    if record is None:
        raise NotFoundError("API token not found")
    if not record.revoked:
        record = await repo.revoke(record, revoked_by)
    return to_out(record)


async def resolve(token: str) -> ApiToken | None:
    """The active (non-revoked) record for a presented token, or None."""
    if not token.startswith(TOKEN_PREFIX):
        return None
    return await repo.get_active_by_hash(hash_token(token))
