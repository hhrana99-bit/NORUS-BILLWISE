from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.deps import (
    AuthPrincipal,
    OrganizationContext,
    get_client_ip,
    get_current_principal,
    require_csrf,
    require_organization_role,
)
from app.db.session import get_db
from app.schemas.tenancy import (
    OrganizationCreateRequest,
    OrganizationDto,
    OrganizationListResponse,
    WorkspaceCreateRequest,
    WorkspaceDetailDto,
    WorkspaceProvisionResponse,
    WorkspaceSettingsDto,
)
from app.services.tenancy_service import (
    create_organization,
    create_workspace_in_organization,
    list_user_organizations,
)

router = APIRouter(prefix="/organizations", tags=["Organizations"])


@router.get(
    "",
    response_model=OrganizationListResponse,
    response_model_by_alias=True,
    summary="List organizations where caller holds active membership",
)
def get_organizations(
    principal: AuthPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> OrganizationListResponse:
    rows = list_user_organizations(db, user_id=principal.user.id)
    return OrganizationListResponse(
        items=[
            OrganizationDto(
                id=org.id,
                name=org.name,
                slug=org.slug,
                firm_type=org.firm_type,
                primary_contact_email=org.primary_contact_email,
                role=membership.role,  # type: ignore[arg-type]
                is_active=org.is_active,
                created_at=org.created_at,
            )
            for org, membership in rows
        ]
    )


@router.post(
    "",
    response_model=OrganizationDto,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
    summary="Create a new organization and assign creator as ORG_OWNER",
)
def post_organization(
    payload: OrganizationCreateRequest,
    request: Request,
    principal: AuthPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> OrganizationDto:
    org, membership = create_organization(
        db,
        creator=principal.user,
        payload=payload,
        ip_address=get_client_ip(request),
    )
    return OrganizationDto(
        id=org.id,
        name=org.name,
        slug=org.slug,
        firm_type=org.firm_type,
        primary_contact_email=org.primary_contact_email,
        role=membership.role,  # type: ignore[arg-type]
        is_active=org.is_active,
        created_at=org.created_at,
    )


@router.post(
    "/{organizationId}/workspaces",
    response_model=WorkspaceProvisionResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
    summary="Provision a client workspace and locked-human-review settings under an organization",
)
def post_organization_workspace(
    payload: WorkspaceCreateRequest,
    request: Request,
    org_ctx: OrganizationContext = Depends(
        require_organization_role("ORG_OWNER", "ORG_ADMIN")
    ),
    db: Session = Depends(get_db),
) -> WorkspaceProvisionResponse:
    workspace, settings, membership = create_workspace_in_organization(
        db,
        organization=org_ctx.organization,
        creator=org_ctx.principal.user,
        payload=payload,
        ip_address=get_client_ip(request),
    )
    return WorkspaceProvisionResponse(
        workspace=WorkspaceDetailDto(
            id=workspace.id,
            organization_id=workspace.organization_id,
            name=workspace.name,
            workspace_code=workspace.workspace_code,
            is_active=workspace.is_active,
            current_user_role=membership.role,  # type: ignore[arg-type]
            created_at=workspace.created_at,
        ),
        settings=WorkspaceSettingsDto.model_validate(settings),
    )
