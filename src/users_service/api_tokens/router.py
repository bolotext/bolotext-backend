from common.enums import Role
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends, Path

from users_service.api_tokens import service
from users_service.api_tokens.schema import ApiTokenCreate, ApiTokenCreated, ApiTokenOut
from users_service.core.deps import AuthContext, require_role

router = APIRouter(prefix="/api-tokens", tags=["api-tokens"])

_super_admin = require_role(Role.SUPER_ADMIN)


@router.post("", response_model=SuccessResponse[ApiTokenCreated], summary="Create an API token")
async def create_api_token(payload: ApiTokenCreate, auth: AuthContext = Depends(_super_admin)) -> dict:
    """Creates a non-expiring API token with the `agent-config:read` scope —
    used by a service (e.g. the voice agent) to read agent configs via the
    Agents service's `GET /agents/config`. The full token is returned **once**
    in this response and cannot be retrieved again; only its hash is stored.

    **Auth:** Super Admin only.

    **Errors:** `FORBIDDEN` for any other role.
    """
    return success_response(code=201, message="API token created", data=await service.create_token(payload.name, auth.user_id))


@router.get("", response_model=SuccessResponse[list[ApiTokenOut]], summary="List API tokens")
async def list_api_tokens(auth: AuthContext = Depends(_super_admin)) -> dict:
    """Lists every API token, newest first, including revoked ones. Never
    includes the token itself.

    **Auth:** Super Admin only.
    """
    return success_response(data=await service.list_tokens())


@router.delete("/{token_id}", response_model=SuccessResponse[ApiTokenOut], summary="Revoke an API token")
async def revoke_api_token(
    token_id: str = Path(description="The API token's id."), auth: AuthContext = Depends(_super_admin)
) -> dict:
    """Revokes a token so it stops working immediately. Idempotent: revoking an
    already-revoked token returns it unchanged.

    **Auth:** Super Admin only.

    **Errors:** `NOT_FOUND` if no such token exists.
    """
    return success_response(message="API token revoked", data=await service.revoke_token(token_id, auth.user_id))
