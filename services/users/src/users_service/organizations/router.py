from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends, Query

from users_service.core.deps import AuthContext, require_permission
from users_service.enums import OrganizationStatus
from users_service.organizations import service as organization_service
from users_service.organizations.model import Organization
from users_service.organizations.schema import (
    OrganizationCreate,
    OrganizationCreateResponse,
    OrganizationOut,
    OrganizationUpdate,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _to_out(org: Organization) -> OrganizationOut:
    return OrganizationOut(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        status=org.status,
        features=org.features,
        created_by=str(org.created_by),
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


@router.post(
    "",
    response_model=SuccessResponse[OrganizationCreateResponse],
    summary="Create a new organization",
)
async def create_organization(
    payload: OrganizationCreate, auth: AuthContext = Depends(require_permission("organization.create"))
) -> dict:
    """Creates a new tenant organization, optionally bootstrapping its first
    Admin user in the same call when `admin_email` is supplied.

    **Auth:** Requires the `organization.create` permission for the caller's
    role.

    **Errors:**
    - `FORBIDDEN` — caller lacks the `organization.create` permission.
    - `CONFLICT` — the `slug` is already in use by another organization.
    - `VALIDATION_ERROR` — `features` is empty or has an unknown value.
    """
    org, admin_user = await organization_service.create_organization(
        name=payload.name,
        slug=payload.slug,
        created_by=auth.user_id,
        admin_email=payload.admin_email,
        admin_full_name=payload.admin_full_name,
        features=payload.features,
    )
    data = OrganizationCreateResponse(
        organization=_to_out(org), admin_user_id=str(admin_user.id) if admin_user else None
    )
    return success_response(code=201, message="Organization created", data=data)


@router.get(
    "",
    response_model=SuccessResponse[list[OrganizationOut]],
    summary="List organizations",
)
async def list_organizations(
    skip: int = Query(0, ge=0, description="Number of organizations to skip, for pagination."),
    limit: int = Query(50, ge=1, description="Maximum number of organizations to return."),
    search: str | None = Query(default=None, description="Case-insensitive substring match against name/slug."),
    status: OrganizationStatus | None = Query(default=None, description="Filter to organizations in this status only."),
    auth: AuthContext = Depends(require_permission("organization.view")),
) -> dict:
    """Lists organizations, optionally filtered by search text and/or
    status.

    **Auth:** Requires the `organization.view` permission for the caller's
    role.

    **Errors:**
    - `FORBIDDEN` — caller lacks the `organization.view` permission.
    """
    orgs = await organization_service.list_organizations(skip=skip, limit=limit, search=search, status=status)
    return success_response(data=[_to_out(o) for o in orgs])


@router.get(
    "/{org_id}",
    response_model=SuccessResponse[OrganizationOut],
    summary="Get an organization by id",
)
async def get_organization(
    org_id: PydanticObjectId, auth: AuthContext = Depends(require_permission("organization.view"))
) -> dict:
    """Fetches a single organization's details.

    **Auth:** Requires the `organization.view` permission for the caller's
    role.

    **Errors:**
    - `FORBIDDEN` — caller lacks the `organization.view` permission.
    - `NOT_FOUND` — no organization with this id exists.
    """
    org = await organization_service.get_organization(org_id)
    return success_response(data=_to_out(org))


@router.patch(
    "/{org_id}",
    response_model=SuccessResponse[OrganizationOut],
    summary="Update an organization",
)
async def update_organization(
    org_id: PydanticObjectId,
    payload: OrganizationUpdate,
    auth: AuthContext = Depends(require_permission("organization.update")),
) -> dict:
    """Updates an organization's name, status (e.g. suspending it) and/or the
    product areas (`features`) it may use. Only the fields supplied are changed.

    **Auth:** Requires the `organization.update` permission for the caller's
    role.

    **Errors:**
    - `FORBIDDEN` — caller lacks the `organization.update` permission.
    - `NOT_FOUND` — no organization with this id exists.
    """
    org = await organization_service.update_organization(
        org_id, name=payload.name, status=payload.status, features=payload.features
    )
    return success_response(message="Organization updated", data=_to_out(org))
