from beanie import PydanticObjectId
from common.responses import success_response
from common.schemas import SuccessResponse
from fastapi import APIRouter, Depends

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
        created_by=str(org.created_by),
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


@router.post("", response_model=SuccessResponse[OrganizationCreateResponse])
async def create_organization(
    payload: OrganizationCreate, auth: AuthContext = Depends(require_permission("organization.create"))
) -> dict:
    org, admin_user = await organization_service.create_organization(
        name=payload.name,
        slug=payload.slug,
        created_by=auth.user_id,
        admin_email=payload.admin_email,
        admin_password=payload.admin_password,
        admin_full_name=payload.admin_full_name,
    )
    data = OrganizationCreateResponse(
        organization=_to_out(org), admin_user_id=str(admin_user.id) if admin_user else None
    )
    return success_response(code=201, message="Organization created", data=data)


@router.get("", response_model=SuccessResponse[list[OrganizationOut]])
async def list_organizations(
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
    status: OrganizationStatus | None = None,
    auth: AuthContext = Depends(require_permission("organization.view")),
) -> dict:
    orgs = await organization_service.list_organizations(skip=skip, limit=limit, search=search, status=status)
    return success_response(data=[_to_out(o) for o in orgs])


@router.get("/{org_id}", response_model=SuccessResponse[OrganizationOut])
async def get_organization(
    org_id: PydanticObjectId, auth: AuthContext = Depends(require_permission("organization.view"))
) -> dict:
    org = await organization_service.get_organization(org_id)
    return success_response(data=_to_out(org))


@router.patch("/{org_id}", response_model=SuccessResponse[OrganizationOut])
async def update_organization(
    org_id: PydanticObjectId,
    payload: OrganizationUpdate,
    auth: AuthContext = Depends(require_permission("organization.update")),
) -> dict:
    org = await organization_service.update_organization(org_id, name=payload.name, status=payload.status)
    return success_response(message="Organization updated", data=_to_out(org))
