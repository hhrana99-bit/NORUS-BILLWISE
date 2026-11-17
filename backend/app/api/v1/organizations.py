from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Path, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import (
    AuthPrincipal,
    OrganizationContext,
    get_app_settings,
    get_client_ip,
    get_current_principal,
    require_csrf,
    require_organization_role,
)
from app.db.session import get_db
from app.models.tenancy import OrganizationInvitation
from app.schemas.tenancy import (
    OrganizationCreateRequest,
    OrganizationDto,
    OrganizationInvitationAcceptRequest,
    OrganizationInvitationCreateRequest,
    OrganizationInvitationDto,
    OrganizationListResponse,
    OrganizationMembershipDto,
    OrganizationMembershipListResponse,
    OrganizationMembershipUpdateRequest,
    WorkspaceCreateRequest,
    WorkspaceDetailDto,
    WorkspaceProvisionResponse,
    WorkspaceSettingsDto,
)
from app.services.tenancy_service import (
    accept_organization_invitation,
    create_organization,
    create_organization_invitation,
    create_workspace_in_organization,
    list_organization_invitations,
    list_organization_memberships,
    list_user_organizations,
    remove_organization_membership,
    revoke_organization_invitation,
    update_organization_membership,
)

router = APIRouter(prefix="/organizations", tags=["Organizations"])


def _invitation_status(inv: OrganizationInvitation) -> str:
    if inv.accepted_at is not None:
        return "ACCEPTED"
    if inv.revoked_at is not None:
        return "REVOKED"
    expires_at = (
        inv.expires_at.replace(tzinfo=timezone.utc)
        if inv.expires_at.tzinfo is None
        else inv.expires_at.astimezone(timezone.utc)
    )
    if expires_at <= datetime.now(timezone.utc):
        return "EXPIRED"
    return "PENDING"


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
    "/invitations/accept",
    response_model=OrganizationDto,
    response_model_by_alias=True,
    dependencies=[Depends(require_csrf)],
    summary="Accept an organization invitation matching the caller's verified email",
)
def post_accept_organization_invitation(
    payload: OrganizationInvitationAcceptRequest,
    request: Request,
    principal: AuthPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> OrganizationDto:
    org, membership = accept_organization_invitation(
        db,
        raw_token=payload.token,
        user=principal.user,
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


@router.get(
    "/{organizationId}/memberships",
    response_model=OrganizationMembershipListResponse,
    response_model_by_alias=True,
    summary="List organization memberships (ORG_OWNER, ORG_ADMIN)",
)
def get_organization_memberships(
    org_ctx: OrganizationContext = Depends(
        require_organization_role("ORG_OWNER", "ORG_ADMIN")
    ),
    db: Session = Depends(get_db),
) -> OrganizationMembershipListResponse:
    rows = list_organization_memberships(db, organization_id=org_ctx.organization.id)
    return OrganizationMembershipListResponse(
        items=[
            OrganizationMembershipDto(
                id=membership.id,
                organization_id=membership.organization_id,
                user_id=user.id,
                email=user.email,
                full_name=user.full_name,
                role=membership.role,  # type: ignore[arg-type]
                status=membership.status,  # type: ignore[arg-type]
                created_at=membership.created_at,
                updated_at=membership.updated_at,
            )
            for membership, user in rows
        ]
    )


@router.patch(
    "/{organizationId}/memberships/{membershipId}",
    response_model=OrganizationMembershipDto,
    response_model_by_alias=True,
    dependencies=[Depends(require_csrf)],
    summary="Update organization membership role/status with session revocation & owner protection",
)
def patch_organization_membership(
    payload: OrganizationMembershipUpdateRequest,
    request: Request,
    membership_id: uuid.UUID = Path(..., alias="membershipId"),
    org_ctx: OrganizationContext = Depends(
        require_organization_role("ORG_OWNER", "ORG_ADMIN")
    ),
    db: Session = Depends(get_db),
) -> OrganizationMembershipDto:
    membership, target_user = update_organization_membership(
        db,
        organization=org_ctx.organization,
        membership_id=membership_id,
        actor=org_ctx.principal.user,
        actor_membership=org_ctx.membership,
        payload=payload,
        ip_address=get_client_ip(request),
    )
    return OrganizationMembershipDto(
        id=membership.id,
        organization_id=membership.organization_id,
        user_id=target_user.id,
        email=target_user.email,
        full_name=target_user.full_name,
        role=membership.role,  # type: ignore[arg-type]
        status=membership.status,  # type: ignore[arg-type]
        created_at=membership.created_at,
        updated_at=membership.updated_at,
    )


@router.delete(
    "/{organizationId}/memberships/{membershipId}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    summary="Remove organization membership and cascade-remove workspace access & sessions",
)
def delete_organization_membership(
    request: Request,
    membership_id: uuid.UUID = Path(..., alias="membershipId"),
    org_ctx: OrganizationContext = Depends(
        require_organization_role("ORG_OWNER", "ORG_ADMIN")
    ),
    db: Session = Depends(get_db),
) -> Response:
    remove_organization_membership(
        db,
        organization=org_ctx.organization,
        membership_id=membership_id,
        actor=org_ctx.principal.user,
        actor_membership=org_ctx.membership,
        ip_address=get_client_ip(request),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{organizationId}/invitations",
    response_model=list[OrganizationInvitationDto],
    response_model_by_alias=True,
    summary="List organization invitations (ORG_OWNER, ORG_ADMIN)",
)
def get_organization_invitations(
    org_ctx: OrganizationContext = Depends(
        require_organization_role("ORG_OWNER", "ORG_ADMIN")
    ),
    db: Session = Depends(get_db),
) -> list[OrganizationInvitationDto]:
    rows = list_organization_invitations(db, organization_id=org_ctx.organization.id)
    return [
        OrganizationInvitationDto(
            id=inv.id,
            organization_id=inv.organization_id,
            invited_email=inv.invited_email,
            role=inv.role,  # type: ignore[arg-type]
            status=_invitation_status(inv),  # type: ignore[arg-type]
            expires_at=inv.expires_at,
            created_at=inv.created_at,
            invite_token=None,
        )
        for inv in rows
    ]


@router.post(
    "/{organizationId}/invitations",
    response_model=OrganizationInvitationDto,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
    summary="Issue an anti-enumeration organization onboarding invitation",
)
def post_organization_invitation(
    payload: OrganizationInvitationCreateRequest,
    request: Request,
    org_ctx: OrganizationContext = Depends(
        require_organization_role("ORG_OWNER", "ORG_ADMIN")
    ),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> OrganizationInvitationDto:
    inv, raw_token = create_organization_invitation(
        db,
        organization=org_ctx.organization,
        actor=org_ctx.principal.user,
        payload=payload,
        settings=settings,
        ip_address=get_client_ip(request),
    )
    return OrganizationInvitationDto(
        id=inv.id,
        organization_id=inv.organization_id,
        invited_email=inv.invited_email,
        role=inv.role,  # type: ignore[arg-type]
        status=_invitation_status(inv),  # type: ignore[arg-type]
        expires_at=inv.expires_at,
        created_at=inv.created_at,
        invite_token=raw_token,
    )


@router.delete(
    "/{organizationId}/invitations/{invitationId}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    summary="Revoke a pending organization invitation",
)
def delete_organization_invitation(
    request: Request,
    invitation_id: uuid.UUID = Path(..., alias="invitationId"),
    org_ctx: OrganizationContext = Depends(
        require_organization_role("ORG_OWNER", "ORG_ADMIN")
    ),
    db: Session = Depends(get_db),
) -> Response:
    revoke_organization_invitation(
        db,
        organization=org_ctx.organization,
        invitation_id=invitation_id,
        actor=org_ctx.principal.user,
        ip_address=get_client_ip(request),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
