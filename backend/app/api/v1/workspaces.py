from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.deps import (
    AuthPrincipal,
    WorkspaceContext,
    get_client_ip,
    get_current_principal,
    require_csrf,
    require_workspace_role,
)
from app.db.session import get_db
from app.schemas.tenancy import (
    AuditEventDto,
    AuditEventListResponse,
    MembershipCreateRequest,
    MembershipDto,
    MembershipListResponse,
    MembershipUpdateRequest,
    WorkspaceDetailDto,
    WorkspaceListItemDto,
    WorkspaceListResponse,
    WorkspaceSettingsDto,
    WorkspaceSettingsUpdateRequest,
)
from app.services.audit_service import list_workspace_audit_events
from app.services.tenancy_service import (
    add_workspace_membership,
    get_workspace_settings,
    list_user_workspaces,
    list_workspace_memberships,
    remove_workspace_membership,
    update_workspace_membership,
    update_workspace_settings,
)

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


@router.get(
    "",
    response_model=WorkspaceListResponse,
    response_model_by_alias=True,
    summary="List active workspaces accessible to the authenticated user",
)
def get_workspaces(
    organization_id: uuid.UUID | None = Query(default=None, alias="organizationId"),
    principal: AuthPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> WorkspaceListResponse:
    rows = list_user_workspaces(
        db,
        user_id=principal.user.id,
        organization_id=organization_id,
    )
    return WorkspaceListResponse(
        items=[
            WorkspaceListItemDto(
                id=ws.id,
                organization_id=ws.organization_id,
                name=ws.name,
                workspace_code=ws.workspace_code,
                role=membership.role,  # type: ignore[arg-type]
                is_active=ws.is_active,
                created_at=ws.created_at,
            )
            for ws, membership in rows
        ]
    )


@router.get(
    "/{workspaceId}",
    response_model=WorkspaceDetailDto,
    response_model_by_alias=True,
    summary="Fetch workspace metadata and caller's effective workspace role",
)
def get_workspace_detail(
    ws_ctx: WorkspaceContext = Depends(
        require_workspace_role("WORKSPACE_ADMIN", "REVIEWER", "UPLOADER", "VIEWER")
    ),
) -> WorkspaceDetailDto:
    ws = ws_ctx.workspace
    return WorkspaceDetailDto(
        id=ws.id,
        organization_id=ws.organization_id,
        name=ws.name,
        workspace_code=ws.workspace_code,
        is_active=ws.is_active,
        current_user_role=ws_ctx.membership.role,  # type: ignore[arg-type]
        created_at=ws.created_at,
    )


@router.get(
    "/{workspaceId}/settings",
    response_model=WorkspaceSettingsDto,
    response_model_by_alias=True,
    summary="Retrieve workspace configuration settings",
)
def get_settings_for_workspace(
    ws_ctx: WorkspaceContext = Depends(
        require_workspace_role("WORKSPACE_ADMIN", "REVIEWER", "UPLOADER", "VIEWER")
    ),
    db: Session = Depends(get_db),
) -> WorkspaceSettingsDto:
    settings = get_workspace_settings(db, workspace_id=ws_ctx.workspace.id)
    return WorkspaceSettingsDto.model_validate(settings)


@router.patch(
    "/{workspaceId}/settings",
    response_model=WorkspaceSettingsDto,
    response_model_by_alias=True,
    dependencies=[Depends(require_csrf)],
    summary="Update workspace settings (WORKSPACE_ADMIN only; requireHumanReview stays locked true)",
)
def patch_settings_for_workspace(
    payload: WorkspaceSettingsUpdateRequest,
    request: Request,
    ws_ctx: WorkspaceContext = Depends(require_workspace_role("WORKSPACE_ADMIN")),
    db: Session = Depends(get_db),
) -> WorkspaceSettingsDto:
    updated = update_workspace_settings(
        db,
        workspace=ws_ctx.workspace,
        actor=ws_ctx.principal.user,
        payload=payload,
        ip_address=get_client_ip(request),
    )
    return WorkspaceSettingsDto.model_validate(updated)


@router.get(
    "/{workspaceId}/memberships",
    response_model=MembershipListResponse,
    response_model_by_alias=True,
    summary="List workspace memberships (WORKSPACE_ADMIN, REVIEWER, VIEWER)",
)
def get_memberships(
    ws_ctx: WorkspaceContext = Depends(
        require_workspace_role("WORKSPACE_ADMIN", "REVIEWER", "VIEWER")
    ),
    db: Session = Depends(get_db),
) -> MembershipListResponse:
    rows = list_workspace_memberships(db, workspace_id=ws_ctx.workspace.id)
    return MembershipListResponse(
        items=[
            MembershipDto(
                id=membership.id,
                workspace_id=membership.workspace_id,
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


@router.post(
    "/{workspaceId}/memberships",
    response_model=MembershipDto,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
    summary="Grant a workspace role to an existing active user (WORKSPACE_ADMIN only)",
)
def post_membership(
    payload: MembershipCreateRequest,
    request: Request,
    ws_ctx: WorkspaceContext = Depends(require_workspace_role("WORKSPACE_ADMIN")),
    db: Session = Depends(get_db),
) -> MembershipDto:
    membership, target_user = add_workspace_membership(
        db,
        workspace=ws_ctx.workspace,
        actor=ws_ctx.principal.user,
        payload=payload,
        ip_address=get_client_ip(request),
    )
    return MembershipDto(
        id=membership.id,
        workspace_id=membership.workspace_id,
        user_id=target_user.id,
        email=target_user.email,
        full_name=target_user.full_name,
        role=membership.role,  # type: ignore[arg-type]
        status=membership.status,  # type: ignore[arg-type]
        created_at=membership.created_at,
        updated_at=membership.updated_at,
    )


@router.patch(
    "/{workspaceId}/memberships/{membershipId}",
    response_model=MembershipDto,
    response_model_by_alias=True,
    dependencies=[Depends(require_csrf)],
    summary="Update workspace membership role/status with last-admin protection & session revocation",
)
def patch_membership(
    payload: MembershipUpdateRequest,
    request: Request,
    membership_id: uuid.UUID = Path(..., alias="membershipId"),
    ws_ctx: WorkspaceContext = Depends(require_workspace_role("WORKSPACE_ADMIN")),
    db: Session = Depends(get_db),
) -> MembershipDto:
    membership, target_user = update_workspace_membership(
        db,
        workspace=ws_ctx.workspace,
        membership_id=membership_id,
        actor=ws_ctx.principal.user,
        payload=payload,
        ip_address=get_client_ip(request),
    )
    return MembershipDto(
        id=membership.id,
        workspace_id=membership.workspace_id,
        user_id=target_user.id,
        email=target_user.email,
        full_name=target_user.full_name,
        role=membership.role,  # type: ignore[arg-type]
        status=membership.status,  # type: ignore[arg-type]
        created_at=membership.created_at,
        updated_at=membership.updated_at,
    )


@router.delete(
    "/{workspaceId}/memberships/{membershipId}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    summary="Remove workspace membership with last-admin protection & session revocation",
)
def delete_membership(
    request: Request,
    membership_id: uuid.UUID = Path(..., alias="membershipId"),
    ws_ctx: WorkspaceContext = Depends(require_workspace_role("WORKSPACE_ADMIN")),
    db: Session = Depends(get_db),
) -> Response:
    remove_workspace_membership(
        db,
        workspace=ws_ctx.workspace,
        membership_id=membership_id,
        actor=ws_ctx.principal.user,
        ip_address=get_client_ip(request),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{workspaceId}/audit-events",
    response_model=AuditEventListResponse,
    response_model_by_alias=True,
    summary="Retrieve chronological workspace security and compliance audit events",
)
def get_workspace_audit_events(
    ws_ctx: WorkspaceContext = Depends(
        require_workspace_role("WORKSPACE_ADMIN", "REVIEWER", "UPLOADER", "VIEWER")
    ),
    db: Session = Depends(get_db),
    entity_type: str | None = Query(default=None, alias="entityType"),
    entity_id: uuid.UUID | None = Query(default=None, alias="entityId"),
    event_type: str | None = Query(default=None, alias="eventType"),
    actor_user_id: uuid.UUID | None = Query(default=None, alias="actorUserId"),
    date_from: datetime | None = Query(default=None, alias="dateFrom"),
    date_to: datetime | None = Query(default=None, alias="dateTo"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100, alias="pageSize"),
) -> AuditEventListResponse:
    restrict_actor = (
        ws_ctx.principal.user.id if ws_ctx.membership.role == "UPLOADER" else None
    )
    rows, total = list_workspace_audit_events(
        db,
        workspace_id=ws_ctx.workspace.id,
        restrict_to_actor_user_id=restrict_actor,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        actor_user_id=actor_user_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return AuditEventListResponse(
        items=[
            AuditEventDto(
                id=ev.id,
                organization_id=ev.organization_id,
                workspace_id=ev.workspace_id,
                actor_user_id=ev.actor_user_id,
                actor_display_name=ev.actor_display_name,
                event_type=ev.event_type,
                entity_type=ev.entity_type,
                entity_id=ev.entity_id,
                summary=ev.summary,
                tone=ev.tone,  # type: ignore[arg-type]
                metadata=ev.event_metadata,
                created_at=ev.created_at,
            )
            for ev in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
