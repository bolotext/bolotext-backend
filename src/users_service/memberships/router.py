from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends, Path, Query

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


@router.post(
    "",
    response_model=SuccessResponse[MembershipOut],
    summary="Add an existing user as a member of an organization",
)
async def add_member(
    payload: MembershipCreate,
    org_id: PydanticObjectId = Path(description="The organization to add the member to."),
    auth: AuthContext = Depends(require_permission("membership.create")),
) -> dict:
    """Grants an existing user a role within this organization. The user
    must already exist (see `POST /users` to create one first); this
    endpoint only creates the membership/role link, not the user account.

    **Auth:** Requires the `membership.create` permission for the caller's
    role, and the caller must belong to this organization (or be a Super
    Admin).

    **Errors:**
    - `FORBIDDEN` — caller lacks the `membership.create` permission, or is
      trying to manage an organization other than their own.
    - `BAD_REQUEST` — `role` is not one of the roles assignable within an
      organization (ADMIN, DEVELOPER, QA).
    - `NOT_FOUND` — no organization or user with the given id exists.
    - `CONFLICT` — the user is already a member of this organization.
    """
    user, membership = await membership_service.add_membership(
        auth, org_id, PydanticObjectId(payload.user_id), payload.role
    )
    return success_response(code=201, message="Member added", data=_to_out(user, membership))


@router.get(
    "",
    response_model=SuccessResponse[list[MembershipOut]],
    summary="List an organization's members",
)
async def list_members(
    org_id: PydanticObjectId = Path(description="The organization whose members to list."),
    skip: int = Query(0, ge=0, description="Number of members to skip, for pagination."),
    limit: int = Query(50, ge=1, description="Maximum number of members to return."),
    auth: AuthContext = Depends(require_permission("membership.view")),
) -> dict:
    """Lists the users who are members of this organization, with their
    role.

    **Auth:** Requires the `membership.view` permission for the caller's
    role, and the caller must belong to this organization (or be a Super
    Admin).

    **Errors:**
    - `FORBIDDEN` — caller lacks the `membership.view` permission, or is
      trying to view an organization other than their own.
    """
    members = await membership_service.list_members(auth, org_id, skip=skip, limit=limit)
    return success_response(data=[_to_out(user, membership) for user, membership in members])


@router.patch(
    "/{user_id}",
    response_model=SuccessResponse[MembershipOut],
    summary="Change a member's role",
)
async def update_member(
    payload: MembershipUpdate,
    org_id: PydanticObjectId = Path(description="The organization the membership belongs to."),
    user_id: PydanticObjectId = Path(description="The user whose role to change."),
    auth: AuthContext = Depends(require_permission("membership.update")),
) -> dict:
    """Changes an existing member's role within this organization.

    **Auth:** Requires the `membership.update` permission for the caller's
    role, and the caller must belong to this organization (or be a Super
    Admin).

    **Errors:**
    - `FORBIDDEN` — caller lacks the `membership.update` permission, or is
      trying to manage an organization other than their own.
    - `BAD_REQUEST` — `role` is not one of the roles assignable within an
      organization (ADMIN, DEVELOPER, QA).
    - `NOT_FOUND` — the user is not a member of this organization.
    """
    user, membership = await membership_service.update_membership_role(auth, org_id, user_id, payload.role)
    return success_response(message="Member role updated", data=_to_out(user, membership))


@router.delete(
    "/{user_id}",
    response_model=SuccessResponse[None],
    summary="Remove a member from an organization",
)
async def remove_member(
    org_id: PydanticObjectId = Path(description="The organization the membership belongs to."),
    user_id: PydanticObjectId = Path(description="The user to remove from the organization."),
    auth: AuthContext = Depends(require_permission("membership.delete")),
) -> dict:
    """Removes the user's membership/role in this organization. Does not
    delete the user account itself.

    **Auth:** Requires the `membership.delete` permission for the caller's
    role, and the caller must belong to this organization (or be a Super
    Admin).

    **Errors:**
    - `FORBIDDEN` — caller lacks the `membership.delete` permission, or is
      trying to manage an organization other than their own.
    - `NOT_FOUND` — the user is not a member of this organization.
    """
    await membership_service.remove_membership(auth, org_id, user_id)
    return success_response(message="Member removed")
