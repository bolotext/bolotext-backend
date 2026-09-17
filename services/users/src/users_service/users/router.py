from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from users_service.core.deps import AuthContext, get_current_auth, require_permission
from users_service.enums import UserStatus
from users_service.users import service as user_service
from users_service.users.model import User
from users_service.users.schema import UserCreate, UserOut, UserSelfUpdate, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


def _to_out(user: User) -> UserOut:
    return UserOut(
        id=str(user.id),
        organization_id=str(user.organization_id) if user.organization_id else None,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        status=user.status,
        must_change_password=user.must_change_password,
        created_by=str(user.created_by) if user.created_by else None,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
    )


@router.get("/me", response_model=SuccessResponse[UserOut])
async def get_me(auth: AuthContext = Depends(get_current_auth)) -> dict:
    return success_response(data=_to_out(auth.user))


@router.patch("/me", response_model=SuccessResponse[UserOut])
async def update_me(payload: UserSelfUpdate, auth: AuthContext = Depends(get_current_auth)) -> dict:
    updated = await user_service.update_self(
        auth, full_name=payload.full_name, password=payload.password, current_password=payload.current_password
    )
    return success_response(message="Profile updated", data=_to_out(updated))


@router.post("", response_model=SuccessResponse[UserOut])
async def create_user(
    payload: UserCreate, auth: AuthContext = Depends(require_permission("user.create"))
) -> dict:
    user = await user_service.create_user(
        auth,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        role=payload.role,
        organization_id=payload.organization_id,
    )
    return success_response(code=201, message="User created", data=_to_out(user))


@router.get("", response_model=SuccessResponse[list[UserOut]])
async def list_users(
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
    status: UserStatus | None = None,
    auth: AuthContext = Depends(require_permission("user.view")),
) -> dict:
    users = await user_service.list_users(auth, skip=skip, limit=limit, search=search, status=status)
    return success_response(data=[_to_out(u) for u in users])


@router.get("/{user_id}", response_model=SuccessResponse[UserOut])
async def get_user(
    user_id: PydanticObjectId,
    auth: AuthContext = Depends(require_permission("user.view")),
) -> dict:
    user = await user_service.get_user(auth, user_id)
    return success_response(data=_to_out(user))


@router.patch("/{user_id}", response_model=SuccessResponse[UserOut])
async def update_user(
    user_id: PydanticObjectId,
    payload: UserUpdate,
    auth: AuthContext = Depends(require_permission("user.update")),
) -> dict:
    user = await user_service.update_user(
        auth,
        user_id,
        full_name=payload.full_name,
        role=payload.role,
        status=payload.status,
        password=payload.password,
    )
    return success_response(message="User updated", data=_to_out(user))


@router.delete("/{user_id}", response_model=SuccessResponse[UserOut])
async def disable_user(
    user_id: PydanticObjectId, auth: AuthContext = Depends(require_permission("user.delete"))
) -> dict:
    user = await user_service.disable_user(auth, user_id)
    return success_response(message="User disabled", data=_to_out(user))
