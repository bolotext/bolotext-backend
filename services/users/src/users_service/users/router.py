from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from users_service.core.deps import AuthContext, get_current_auth, require_permission
from users_service.enums import UserStatus
from users_service.memberships import service as membership_service
from users_service.memberships.model import OrganizationMembership
from users_service.memberships.schema import MyOrganizationOut
from users_service.users import service as user_service
from users_service.users.model import User
from users_service.users.schema import UserCreate, UserOut, UserSelfUpdate, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


def _to_out(user: User, membership: OrganizationMembership | None) -> UserOut:
    return UserOut(
        id=str(user.id),
        organization_id=str(membership.organization_id) if membership else None,
        email=user.email,
        full_name=user.full_name,
        role=membership.role if membership else None,
        is_super_admin=user.is_super_admin,
        status=user.status,
        must_change_password=user.must_change_password,
        created_by=str(user.created_by) if user.created_by else None,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
    )


@router.get("/me", response_model=SuccessResponse[UserOut])
async def get_me(auth: AuthContext = Depends(get_current_auth)) -> dict:
    membership = None
    if not auth.is_super_admin:
        membership = OrganizationMembership(
            user_id=auth.user_id, organization_id=auth.organization_id, role=auth.role
        )
    return success_response(data=_to_out(auth.user, membership))


@router.get("/me/organizations", response_model=SuccessResponse[list[MyOrganizationOut]])
async def get_my_organizations(auth: AuthContext = Depends(get_current_auth)) -> dict:
    memberships = await membership_service.list_my_memberships(auth)
    return success_response(
        data=[
            MyOrganizationOut(organization_id=str(org.id), name=org.name, slug=org.slug, role=role)
            for org, role in memberships
        ]
    )


@router.patch("/me", response_model=SuccessResponse[UserOut])
async def update_me(payload: UserSelfUpdate, auth: AuthContext = Depends(get_current_auth)) -> dict:
    updated = await user_service.update_self(
        auth, full_name=payload.full_name, password=payload.password, current_password=payload.current_password
    )
    membership = None
    if not auth.is_super_admin:
        membership = OrganizationMembership(
            user_id=auth.user_id, organization_id=auth.organization_id, role=auth.role
        )
    return success_response(message="Profile updated", data=_to_out(updated, membership))


@router.post("", response_model=SuccessResponse[UserOut])
async def create_user(
    payload: UserCreate, auth: AuthContext = Depends(require_permission("user.create"))
) -> dict:
    user, membership = await user_service.create_user(
        auth,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        role=payload.role,
        organization_id=payload.organization_id,
    )
    return success_response(code=201, message="User created", data=_to_out(user, membership))


@router.get("", response_model=SuccessResponse[list[UserOut]])
async def list_users(
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
    status: UserStatus | None = None,
    auth: AuthContext = Depends(require_permission("user.view")),
) -> dict:
    users = await user_service.list_users(auth, skip=skip, limit=limit, search=search, status=status)
    return success_response(data=[_to_out(user, membership) for user, membership in users])


@router.get("/{user_id}", response_model=SuccessResponse[UserOut])
async def get_user(
    user_id: PydanticObjectId,
    auth: AuthContext = Depends(require_permission("user.view")),
) -> dict:
    user, membership = await user_service.get_user(auth, user_id)
    return success_response(data=_to_out(user, membership))


@router.patch("/{user_id}", response_model=SuccessResponse[UserOut])
async def update_user(
    user_id: PydanticObjectId,
    payload: UserUpdate,
    auth: AuthContext = Depends(require_permission("user.update")),
) -> dict:
    user, membership = await user_service.update_user(
        auth,
        user_id,
        full_name=payload.full_name,
        role=payload.role,
        status=payload.status,
        password=payload.password,
    )
    return success_response(message="User updated", data=_to_out(user, membership))


@router.delete("/{user_id}", response_model=SuccessResponse[UserOut])
async def disable_user(
    user_id: PydanticObjectId, auth: AuthContext = Depends(require_permission("user.delete"))
) -> dict:
    user, membership = await user_service.disable_user(auth, user_id)
    return success_response(message="User disabled", data=_to_out(user, membership))
