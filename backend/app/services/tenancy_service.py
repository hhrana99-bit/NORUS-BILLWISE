from __future__ import annotations

import uuid

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.tenancy import (
    Organization,
    OrganizationMembership,
    User,
    Workspace,
    WorkspaceMembership,
    WorkspaceSettings,
)
from app.schemas.tenancy import (
    MembershipCreateRequest,
    MembershipUpdateRequest,
    OrganizationCreateRequest,
    WorkspaceCreateRequest,
    WorkspaceSettingsUpdateRequest,
)
from app.services.audit_service import record_audit_event
from app.services.auth_service import generate_unique_org_slug, revoke_user_sessions


def list_user_organizations(
    db: Session, *, user_id: uuid.UUID
) -> list[tuple[Organization, OrganizationMembership]]:
    rows = db.execute(
        select(Organization, OrganizationMembership)
        .join(
            OrganizationMembership,
            OrganizationMembership.organization_id == Organization.id,
        )
        .where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.status == "ACTIVE",
            Organization.is_active.is_(True),
        )
        .order_by(Organization.created_at.asc())
    ).all()
    return [(row[0], row[1]) for row in rows]


def create_organization(
    db: Session,
    *,
    creator: User,
    payload: OrganizationCreateRequest,
    ip_address: str | None,
) -> tuple[Organization, OrganizationMembership]:
    org = Organization(
        name=payload.name,
        slug=generate_unique_org_slug(db, payload.name),
        firm_type=payload.firm_type,
        primary_contact_email=payload.primary_contact_email,
        is_active=True,
    )
    db.add(org)
    db.flush()

    membership = OrganizationMembership(
        organization_id=org.id,
        user_id=creator.id,
        role="ORG_OWNER",
        status="ACTIVE",
    )
    db.add(membership)
    db.flush()

    record_audit_event(
        db,
        organization_id=org.id,
        actor_user=creator,
        event_type="organization.created",
        entity_type="organization",
        entity_id=org.id,
        summary=f"Created organization '{org.name}' with owner role.",
        tone="success",
        metadata={"slug": org.slug},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(org)
    return org, membership


def list_user_workspaces(
    db: Session,
    *,
    user_id: uuid.UUID,
    organization_id: uuid.UUID | None = None,
) -> list[tuple[Workspace, WorkspaceMembership]]:
    conditions = [
        WorkspaceMembership.user_id == user_id,
        WorkspaceMembership.status == "ACTIVE",
        Workspace.is_active.is_(True),
        Organization.is_active.is_(True),
    ]
    if organization_id is not None:
        conditions.append(Workspace.organization_id == organization_id)

    rows = db.execute(
        select(Workspace, WorkspaceMembership)
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
        .join(Organization, Organization.id == Workspace.organization_id)
        .where(*conditions)
        .order_by(Workspace.created_at.asc())
    ).all()
    return [(row[0], row[1]) for row in rows]


def create_workspace_in_organization(
    db: Session,
    *,
    organization: Organization,
    creator: User,
    payload: WorkspaceCreateRequest,
    ip_address: str | None,
) -> tuple[Workspace, WorkspaceSettings, WorkspaceMembership]:
    if not payload.require_human_review:
        raise AppError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="HUMAN_REVIEW_CANNOT_BE_DISABLED",
            message="requireHumanReview must remain enabled for all workspaces.",
        )

    existing_code = db.scalar(
        select(Workspace.id).where(
            Workspace.organization_id == organization.id,
            Workspace.workspace_code == payload.workspace_code,
        )
    )
    if existing_code is not None:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="WORKSPACE_CODE_EXISTS",
            message="A workspace with this code already exists in the organization.",
        )

    workspace = Workspace(
        organization_id=organization.id,
        name=payload.name,
        workspace_code=payload.workspace_code,
        is_active=True,
    )
    db.add(workspace)
    db.flush()

    settings = WorkspaceSettings(
        workspace_id=workspace.id,
        legal_entity_name=payload.legal_entity_name,
        company_gstin=payload.company_gstin.strip().upper() if payload.company_gstin else None,
        company_pan=payload.company_pan.strip().upper() if payload.company_pan else None,
        registered_address=payload.registered_address.strip(),
        require_human_review=True,
    )
    db.add(settings)

    membership = WorkspaceMembership(
        workspace_id=workspace.id,
        user_id=creator.id,
        role="WORKSPACE_ADMIN",
        status="ACTIVE",
        invited_by_user_id=creator.id,
    )
    db.add(membership)
    db.flush()

    record_audit_event(
        db,
        organization_id=organization.id,
        workspace_id=workspace.id,
        actor_user=creator,
        event_type="workspace.created",
        entity_type="workspace",
        entity_id=workspace.id,
        summary=f"Provisioned workspace '{workspace.name}' ({workspace.workspace_code}).",
        tone="success",
        metadata={"workspaceCode": workspace.workspace_code},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(workspace)
    db.refresh(settings)
    return workspace, settings, membership


def get_workspace_settings(
    db: Session, *, workspace_id: uuid.UUID
) -> WorkspaceSettings:
    settings = db.get(WorkspaceSettings, workspace_id)
    if settings is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="WORKSPACE_SETTINGS_NOT_FOUND",
            message="Workspace settings could not be found.",
        )
    return settings


def update_workspace_settings(
    db: Session,
    *,
    workspace: Workspace,
    actor: User,
    payload: WorkspaceSettingsUpdateRequest,
    ip_address: str | None,
) -> WorkspaceSettings:
    if payload.require_human_review is False:
        raise AppError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="HUMAN_REVIEW_CANNOT_BE_DISABLED",
            message="requireHumanReview cannot be disabled.",
        )

    settings = get_workspace_settings(db, workspace_id=workspace.id)
    updates = payload.model_dump(exclude_unset=True)
    updates.pop("require_human_review", None)

    for field, value in updates.items():
        if field == "company_gstin" and isinstance(value, str):
            value = value.strip().upper() or None
        elif field == "company_pan" and isinstance(value, str):
            value = value.strip().upper() or None
        elif field == "registered_address" and isinstance(value, str):
            value = value.strip()
        setattr(settings, field, value)

    # Belt-and-suspenders enforcement matching PostgreSQL CHECK constraint
    settings.require_human_review = True

    record_audit_event(
        db,
        organization_id=workspace.organization_id,
        workspace_id=workspace.id,
        actor_user=actor,
        event_type="workspace.settings_updated",
        entity_type="workspace",
        entity_id=workspace.id,
        summary="Updated workspace configuration settings.",
        tone="neutral",
        metadata={"updatedFields": sorted(updates.keys())},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(settings)
    return settings


def list_workspace_memberships(
    db: Session, *, workspace_id: uuid.UUID
) -> list[tuple[WorkspaceMembership, User]]:
    rows = db.execute(
        select(WorkspaceMembership, User)
        .join(User, User.id == WorkspaceMembership.user_id)
        .where(WorkspaceMembership.workspace_id == workspace_id)
        .order_by(WorkspaceMembership.created_at.asc())
    ).all()
    return [(row[0], row[1]) for row in rows]


def add_workspace_membership(
    db: Session,
    *,
    workspace: Workspace,
    actor: User,
    payload: MembershipCreateRequest,
    ip_address: str | None,
) -> tuple[WorkspaceMembership, User]:
    target_user = db.scalar(
        select(User).where(
            func.lower(User.email) == payload.email.strip().lower(),
            User.is_active.is_(True),
        )
    )
    if target_user is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="USER_NOT_FOUND",
            message="Target user account was not found.",
        )

    existing = db.scalar(
        select(WorkspaceMembership.id).where(
            WorkspaceMembership.workspace_id == workspace.id,
            WorkspaceMembership.user_id == target_user.id,
        )
    )
    if existing is not None:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="MEMBERSHIP_ALREADY_EXISTS",
            message="User already holds a membership in this workspace.",
        )

    membership = WorkspaceMembership(
        workspace_id=workspace.id,
        user_id=target_user.id,
        role=payload.role,
        status="ACTIVE",
        invited_by_user_id=actor.id,
    )
    db.add(membership)
    db.flush()

    record_audit_event(
        db,
        organization_id=workspace.organization_id,
        workspace_id=workspace.id,
        actor_user=actor,
        event_type="membership.created",
        entity_type="membership",
        entity_id=membership.id,
        summary=f"Granted workspace role {payload.role} to {target_user.full_name}.",
        tone="success",
        metadata={
            "targetUserId": str(target_user.id),
            "role": payload.role,
        },
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(membership)
    return membership, target_user


def _assert_not_last_active_workspace_admin(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    target_membership: WorkspaceMembership,
) -> None:
    if target_membership.role != "WORKSPACE_ADMIN" or target_membership.status != "ACTIVE":
        return

    active_admins = list(
        db.scalars(
            select(WorkspaceMembership)
            .where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.role == "WORKSPACE_ADMIN",
                WorkspaceMembership.status == "ACTIVE",
            )
            .with_for_update()
        )
    )
    if len(active_admins) <= 1:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="CANNOT_DOWNGRADE_LAST_ADMIN",
            message="Cannot downgrade, suspend, or remove the last active workspace administrator.",
        )


def update_workspace_membership(
    db: Session,
    *,
    workspace: Workspace,
    membership_id: uuid.UUID,
    actor: User,
    payload: MembershipUpdateRequest,
    ip_address: str | None,
) -> tuple[WorkspaceMembership, User]:
    membership = db.scalar(
        select(WorkspaceMembership)
        .where(
            WorkspaceMembership.id == membership_id,
            WorkspaceMembership.workspace_id == workspace.id,
        )
        .with_for_update()
    )
    if membership is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="MEMBERSHIP_NOT_FOUND",
            message="Workspace membership was not found.",
        )

    target_user = db.get(User, membership.user_id)
    if target_user is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="MEMBERSHIP_NOT_FOUND",
            message="Workspace membership user was not found.",
        )

    new_role = payload.role if payload.role is not None else membership.role
    new_status = payload.status if payload.status is not None else membership.status

    losing_admin = (
        membership.role == "WORKSPACE_ADMIN"
        and membership.status == "ACTIVE"
        and (new_role != "WORKSPACE_ADMIN" or new_status != "ACTIVE")
    )
    if losing_admin:
        _assert_not_last_active_workspace_admin(
            db,
            workspace_id=workspace.id,
            target_membership=membership,
        )

    previous_role = membership.role
    previous_status = membership.status
    membership.role = new_role
    membership.status = new_status

    revoked_count = 0
    if new_status == "SUSPENDED" and previous_status != "SUSPENDED":
        revoked_count = revoke_user_sessions(
            db,
            user_id=membership.user_id,
            reason="MEMBERSHIP_SUSPENDED",
        )
    elif new_role != previous_role:
        revoked_count = revoke_user_sessions(
            db,
            user_id=membership.user_id,
            reason="MEMBERSHIP_ROLE_CHANGED",
        )

    event_type = "membership.suspended" if new_status == "SUSPENDED" else "membership.updated"
    record_audit_event(
        db,
        organization_id=workspace.organization_id,
        workspace_id=workspace.id,
        actor_user=actor,
        event_type=event_type,
        entity_type="membership",
        entity_id=membership.id,
        summary=(
            f"Updated membership for {target_user.full_name} "
            f"(role {previous_role} -> {new_role}, status {previous_status} -> {new_status})."
        ),
        tone="warning" if new_status == "SUSPENDED" else "neutral",
        metadata={
            "targetUserId": str(target_user.id),
            "previousRole": previous_role,
            "newRole": new_role,
            "previousStatus": previous_status,
            "newStatus": new_status,
            "revokedSessions": revoked_count,
        },
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(membership)
    return membership, target_user


def remove_workspace_membership(
    db: Session,
    *,
    workspace: Workspace,
    membership_id: uuid.UUID,
    actor: User,
    ip_address: str | None,
) -> None:
    membership = db.scalar(
        select(WorkspaceMembership)
        .where(
            WorkspaceMembership.id == membership_id,
            WorkspaceMembership.workspace_id == workspace.id,
        )
        .with_for_update()
    )
    if membership is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="MEMBERSHIP_NOT_FOUND",
            message="Workspace membership was not found.",
        )

    _assert_not_last_active_workspace_admin(
        db,
        workspace_id=workspace.id,
        target_membership=membership,
    )

    target_user = db.get(User, membership.user_id)
    revoked_count = revoke_user_sessions(
        db,
        user_id=membership.user_id,
        reason="MEMBERSHIP_REMOVED",
    )

    record_audit_event(
        db,
        organization_id=workspace.organization_id,
        workspace_id=workspace.id,
        actor_user=actor,
        event_type="membership.removed",
        entity_type="membership",
        entity_id=membership.id,
        summary=(
            f"Removed workspace membership for "
            f"{target_user.full_name if target_user else str(membership.user_id)}."
        ),
        tone="warning",
        metadata={
            "targetUserId": str(membership.user_id),
            "removedRole": membership.role,
            "revokedSessions": revoked_count,
        },
        ip_address=ip_address,
    )
    db.delete(membership)
    db.commit()
