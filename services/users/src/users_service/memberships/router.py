from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

from users_service.core.deps import AuthContext, require_permission
from users_service.memberships import service as membership_service
from users_service.memberships.model import OrganizationMembership
from users_service.memberships.schema import MembershipCreate, MembershipOut, MembershipUpdate
from users_service.users.model import User

router = APIRouter(prefix="/organizations/{org_id}/members", tags=["memberships"])


def _to_out(user: User, membership: OrganizationMembership) -> MembershipOut:
    return MembershipOut(
        user_id=str(user.id),
        organization_id=str(membership.organization_id),
        email=user.email,
        full_name=user.full_name,
        role=membership.role,
        created_at=membership.created_at,
    )


@router.post("", response_model=SuccessResponse[MembershipOut])
async def add_member(
    org_id: PydanticObjectId,
    payload: MembershipCreate,
    auth: AuthContext = Depends(require_permission("membership.create")),
) -> dict:
    user, membership = await membership_service.add_membership(
        auth, org_id, PydanticObjectId(payload.user_id), payload.role
    )
    return success_response(code=201, message="Member added", data=_to_out(user, membership))


@router.get("", response_model=SuccessResponse[list[MembershipOut]])
async def list_members(
    org_id: PydanticObjectId,
    skip: int = 0,
    limit: int = 50,
    auth: AuthContext = Depends(require_permission("membership.view")),
) -> dict:
    members = await membership_service.list_members(auth, org_id, skip=skip, limit=limit)
    return success_response(data=[_to_out(user, membership) for user, membership in members])


@router.patch("/{user_id}", response_model=SuccessResponse[MembershipOut])
async def update_member(
    org_id: PydanticObjectId,
    user_id: PydanticObjectId,
    payload: MembershipUpdate,
    auth: AuthContext = Depends(require_permission("membership.update")),
) -> dict:
    user, membership = await membership_service.update_membership_role(auth, org_id, user_id, payload.role)
    return success_response(message="Member role updated", data=_to_out(user, membership))


@router.delete("/{user_id}", response_model=SuccessResponse[None])
async def remove_member(
    org_id: PydanticObjectId,
    user_id: PydanticObjectId,
    auth: AuthContext = Depends(require_permission("membership.delete")),
) -> dict:
    await membership_service.remove_membership(auth, org_id, user_id)
    return success_response(message="Member removed")
