from datetime import datetime, timezone

from beanie import PydanticObjectId

from users_service.api_tokens.model import ApiToken


async def create(
    name: str, token_prefix: str, token_hash: str, scopes: list[str], created_by: PydanticObjectId
) -> ApiToken:
    record = ApiToken(name=name, token_prefix=token_prefix, token_hash=token_hash, scopes=scopes, created_by=created_by)
    await record.insert()
    return record


async def list_all() -> list[ApiToken]:
    return await ApiToken.find_all().sort("-created_at").to_list()


async def get(token_id: PydanticObjectId) -> ApiToken | None:
    return await ApiToken.get(token_id)


async def get_active_by_hash(token_hash: str) -> ApiToken | None:
    return await ApiToken.find_one(ApiToken.token_hash == token_hash, ApiToken.revoked == False)  # noqa: E712


async def revoke(record: ApiToken, revoked_by: PydanticObjectId) -> ApiToken:
    record.revoked = True
    record.revoked_at = datetime.now(timezone.utc)
    record.revoked_by = revoked_by
    await record.save()
    return record
