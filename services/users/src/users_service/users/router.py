from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends, Path, Query

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


@router.get(
    "/me",
    response_model=SuccessResponse[UserOut],
    summary="Get the caller's own profile",
)
async def get_me(auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Returns the currently authenticated user's own profile and role in
    the organization their access token is scoped to.

    **Auth:** Bearer access token required (any authenticated user).

    **Errors:**
    - `UNAUTHORIZED` — missing/invalid/expired access token.
    """
    membership = None
    if not auth.is_super_admin:
        membership = OrganizationMembership(
            user_id=auth.user_id, organization_id=auth.organization_id, role=auth.role
        )
    return success_response(data=_to_out(auth.user, membership))


@router.get(
    "/me/organizations",
    response_model=SuccessResponse[list[MyOrganizationOut]],
    summary="List organizations the caller belongs to",
)
async def get_my_organizations(auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Lists every organization the currently authenticated user is a
    member of, with their role in each. Useful for building an organization
    switcher before calling `POST /auth/switch-organization`.

    **Auth:** Bearer access token required (any authenticated user).

    **Errors:**
    - `UNAUTHORIZED` — missing/invalid/expired access token.
    """
    memberships = await membership_service.list_my_memberships(auth)
    return success_response(
        data=[
            MyOrganizationOut(organization_id=str(org.id), name=org.name, slug=org.slug, role=role)
            for org, role in memberships
        ]
    )


@router.patch(
    "/me",
    response_model=SuccessResponse[UserOut],
    summary="Update the caller's own profile",
)
async def update_me(payload: UserSelfUpdate, auth: AuthContext = Depends(get_current_auth)) -> dict:
    """Updates the caller's own name and/or password. Changing the password
    requires `current_password` and revokes all of the caller's existing
    refresh tokens (every other logged-in session is signed out).

    **Auth:** Bearer access token required (any authenticated user).

    **Errors:**
    - `UNAUTHORIZED` — missing/invalid/expired access token, or `password`
      was supplied with a missing/incorrect `current_password`.
    """
    updated = await user_service.update_self(
        auth, full_name=payload.full_name, password=payload.password, current_password=payload.current_password
    )
    membership = None
    if not auth.is_super_admin:
        membership = OrganizationMembership(
            user_id=auth.user_id, organization_id=auth.organization_id, role=auth.role
        )
    return success_response(message="Profile updated", data=_to_out(updated, membership))


@router.post(
    "",
    response_model=SuccessResponse[UserOut],
    summary="Create a new user",
)
async def create_user(
    payload: UserCreate, auth: AuthContext = Depends(require_permission("user.create"))
) -> dict:
    """Creates a new user account and adds it as a member of an
    organization with the given role. A Super Admin caller must specify
    `organization_id`; an org-scoped caller always creates the user in their
    own organization (any `organization_id` they send is ignored).

    **Auth:** Requires the `user.create` permission for the caller's role.

    **Errors:**
    - `FORBIDDEN` — caller lacks the `user.create` permission.
    - `BAD_REQUEST` — `role` is not one of ADMIN, DEVELOPER, QA; or the
      caller is a Super Admin and omitted/sent an invalid `organization_id`.
    - `NOT_FOUND` — `organization_id` doesn't match an existing organization.
    - `CONFLICT` — a user with this email already exists.
    """
    user, membership = await user_service.create_user(
        auth,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        role=payload.role,
        organization_id=payload.organization_id,
    )
    return success_response(code=201, message="User created", data=_to_out(user, membership))


@router.get(
    "",
    response_model=SuccessResponse[list[UserOut]],
    summary="List users",
)
async def list_users(
    skip: int = Query(0, ge=0, description="Number of users to skip, for pagination."),
    limit: int = Query(50, ge=1, description="Maximum number of users to return."),
    search: str | None = Query(default=None, description="Case-insensitive substring match against email/name."),
    status: UserStatus | None = Query(default=None, description="Filter to users in this status only."),
    auth: AuthContext = Depends(require_permission("user.view")),
) -> dict:
    """Lists users. A Super Admin sees users across every organization
    (each with `organization_id`/`role` as `null`, since there's no single
    org context); any other caller sees only users in their own
    organization.

    **Auth:** Requires the `user.view` permission for the caller's role. QA
    callers can never list users, regardless of permission.

    **Errors:**
    - `FORBIDDEN` — caller lacks the `user.view` permission, or has the QA
      role.
    """
    users = await user_service.list_users(auth, skip=skip, limit=limit, search=search, status=status)
    return success_response(data=[_to_out(user, membership) for user, membership in users])


@router.get(
    "/{user_id}",
    response_model=SuccessResponse[UserOut],
    summary="Get a user by id",
)
async def get_user(
    user_id: PydanticObjectId = Path(description="The user to fetch."),
    auth: AuthContext = Depends(require_permission("user.view")),
) -> dict:
    """Fetches a single user. A Super Admin can fetch any user; any other
    caller can only fetch users within their own organization.

    **Auth:** Requires the `user.view` permission for the caller's role. QA
    callers can never view other users, regardless of permission.

    **Errors:**
    - `FORBIDDEN` — caller lacks the `user.view` permission, or has the QA
      role.
    - `NOT_FOUND` — no such user exists (or isn't in the caller's
      organization).
    """
    user, membership = await user_service.get_user(auth, user_id)
    return success_response(data=_to_out(user, membership))


@router.patch(
    "/{user_id}",
    response_model=SuccessResponse[UserOut],
    summary="Update a user",
)
async def update_user(
    payload: UserUpdate,
    user_id: PydanticObjectId = Path(description="The user to update."),
    auth: AuthContext = Depends(require_permission("user.update")),
) -> dict:
    """Updates another user's name, role, status, and/or resets their
    password. Only the fields supplied are changed. Resetting the password
    revokes all of that user's existing refresh tokens (every one of their
    logged-in sessions is signed out).

    A Super Admin changing `role` is only allowed when the target user
    belongs to exactly one organization (otherwise which membership to
    update is ambiguous) — for a multi-org user, use
    `PATCH /organizations/{organization_id}/members/{user_id}` instead.

    **Auth:** Requires the `user.update` permission for the caller's role.

    **Errors:**
    - `FORBIDDEN` — caller lacks the `user.update` permission.
    - `BAD_REQUEST` — `role` is not one of ADMIN, DEVELOPER, QA; or a Super
      Admin tried to change the role of a user in zero or multiple
      organizations.
    - `NOT_FOUND` — no such user exists (or isn't in the caller's
      organization).
    """
    user, membership = await user_service.update_user(
        auth,
        user_id,
        full_name=payload.full_name,
        role=payload.role,
        status=payload.status,
        password=payload.password,
    )
    return success_response(message="User updated", data=_to_out(user, membership))


@router.delete(
    "/{user_id}",
    response_model=SuccessResponse[UserOut],
    summary="Disable a user",
)
async def disable_user(
    user_id: PydanticObjectId = Path(description="The user to disable."),
    auth: AuthContext = Depends(require_permission("user.delete")),
) -> dict:
    """Sets a user's status to `disabled` and revokes all of their refresh
    tokens, immediately signing them out everywhere and blocking future
    logins. This is a soft delete — the account and its history are kept,
    not removed.

    **Auth:** Requires the `user.delete` permission for the caller's role.

    **Errors:**
    - `FORBIDDEN` — caller lacks the `user.delete` permission.
    - `NOT_FOUND` — no such user exists (or isn't in the caller's
      organization).
    """
    user, membership = await user_service.disable_user(auth, user_id)
    return success_response(message="User disabled", data=_to_out(user, membership))
