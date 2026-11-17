from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import hash_refresh_token
from app.models.tenancy import (
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    User,
    Workspace,
    WorkspaceMembership,
    WorkspaceSettings,
    utc_now,
)
from app.schemas.tenancy import (
    MembershipCreateRequest,
    MembershipUpdateRequest,
    OrganizationCreateRequest,
    OrganizationInvitationCreateRequest,
    OrganizationMembershipUpdateRequest,
    WorkspaceCreateRequest,
    WorkspaceSettingsUpdateRequest,
)
from app.services.audit_service import record_audit_event
from app.services.auth_service import generate_unique_org_slug, revoke_user_sessions


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _get_constraint_name(exc: IntegrityError) -> str | None:
    return getattr(getattr(exc.orig, "diag", None), "constraint_name", None)


def _lock_organization_for_mutation(db: Session, organization_id: uuid.UUID) -> None:
    """Acquire deterministic row lock on parent Organization before org membership checks/mutations."""
    db.scalar(
        select(Organization.id)
        .where(Organization.id == organization_id)
        .with_for_update()
    )


def _lock_workspace_for_mutation(db: Session, workspace_id: uuid.UUID) -> None:
    """Acquire deterministic row lock on parent Workspace before membership/admin checks/mutations."""
    db.scalar(
        select(Workspace.id)
        .where(Workspace.id == workspace_id)
        .with_for_update()
    )


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
    org: Organization | None = None
    for attempt in range(4):
        slug = (
            generate_unique_org_slug(db, payload.name)
            if attempt == 0
            else f"{generate_unique_org_slug(db, payload.name)[:70]}-{secrets.token_hex(4)}"
        )
        candidate = Organization(
            name=payload.name,
            slug=slug,
            firm_type=payload.firm_type,
            primary_contact_email=payload.primary_contact_email,
            is_active=True,
        )
        try:
            with db.begin_nested():
                db.add(candidate)
                db.flush()
            org = candidate
            break
        except IntegrityError as exc:
            if _get_constraint_name(exc) == "uq_organizations_slug" and attempt < 3:
                continue
            db.rollback()
            if _get_constraint_name(exc) == "uq_organizations_slug":
                raise AppError(
                    status_code=status.HTTP_409_CONFLICT,
                    code="ORGANIZATION_SLUG_CONFLICT",
                    message="Could not allocate a unique organization slug; please retry.",
                ) from exc
            raise

    assert org is not None

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


def list_organization_memberships(
    db: Session, *, organization_id: uuid.UUID
) -> list[tuple[OrganizationMembership, User]]:
    rows = db.execute(
        select(OrganizationMembership, User)
        .join(User, User.id == OrganizationMembership.user_id)
        .where(OrganizationMembership.organization_id == organization_id)
        .order_by(OrganizationMembership.created_at.asc())
    ).all()
    return [(row[0], row[1]) for row in rows]


def _assert_not_last_active_org_owner(
    db: Session,
    *,
    organization_id: uuid.UUID,
    target_membership: OrganizationMembership,
) -> None:
    if target_membership.role != "ORG_OWNER" or target_membership.status != "ACTIVE":
        return

    active_owners = list(
        db.scalars(
            select(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.role == "ORG_OWNER",
                OrganizationMembership.status == "ACTIVE",
            )
            .order_by(OrganizationMembership.id.asc())
            .with_for_update()
        )
    )
    if len(active_owners) <= 1:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="CANNOT_DOWNGRADE_LAST_ORG_OWNER",
            message="Cannot downgrade, suspend, or remove the last active organization owner.",
        )


def update_organization_membership(
    db: Session,
    *,
    organization: Organization,
    membership_id: uuid.UUID,
    actor: User,
    actor_membership: OrganizationMembership,
    payload: OrganizationMembershipUpdateRequest,
    ip_address: str | None,
) -> tuple[OrganizationMembership, User]:
    _lock_organization_for_mutation(db, organization.id)

    membership = db.scalar(
        select(OrganizationMembership)
        .where(
            OrganizationMembership.id == membership_id,
            OrganizationMembership.organization_id == organization.id,
        )
        .with_for_update()
    )
    if membership is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ORGANIZATION_MEMBERSHIP_NOT_FOUND",
            message="Organization membership was not found.",
        )

    if actor_membership.role != "ORG_OWNER" and (
        membership.role == "ORG_OWNER" or payload.role == "ORG_OWNER"
    ):
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN_ROLE",
            message="Only an organization owner can manage ORG_OWNER assignments.",
        )

    target_user = db.get(User, membership.user_id)
    if target_user is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ORGANIZATION_MEMBERSHIP_NOT_FOUND",
            message="Organization membership user was not found.",
        )

    new_role = payload.role if payload.role is not None else membership.role
    new_status = payload.status if payload.status is not None else membership.status

    losing_owner = (
        membership.role == "ORG_OWNER"
        and membership.status == "ACTIVE"
        and (new_role != "ORG_OWNER" or new_status != "ACTIVE")
    )
    if losing_owner:
        _assert_not_last_active_org_owner(
            db,
            organization_id=organization.id,
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
            reason="ORGANIZATION_MEMBERSHIP_SUSPENDED",
        )
    elif new_role != previous_role:
        revoked_count = revoke_user_sessions(
            db,
            user_id=membership.user_id,
            reason="ORGANIZATION_MEMBERSHIP_ROLE_CHANGED",
        )

    event_type = (
        "organization.membership_suspended"
        if new_status == "SUSPENDED"
        else "organization.membership_updated"
    )
    record_audit_event(
        db,
        organization_id=organization.id,
        actor_user=actor,
        event_type=event_type,
        entity_type="organization_membership",
        entity_id=membership.id,
        summary=(
            f"Updated organization membership for {target_user.full_name} "
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


def remove_organization_membership(
    db: Session,
    *,
    organization: Organization,
    membership_id: uuid.UUID,
    actor: User,
    actor_membership: OrganizationMembership,
    ip_address: str | None,
) -> None:
    _lock_organization_for_mutation(db, organization.id)

    membership = db.scalar(
        select(OrganizationMembership)
        .where(
            OrganizationMembership.id == membership_id,
            OrganizationMembership.organization_id == organization.id,
        )
        .with_for_update()
    )
    if membership is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ORGANIZATION_MEMBERSHIP_NOT_FOUND",
            message="Organization membership was not found.",
        )

    if actor_membership.role != "ORG_OWNER" and membership.role == "ORG_OWNER":
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN_ROLE",
            message="Only an organization owner can remove an ORG_OWNER.",
        )

    _assert_not_last_active_org_owner(
        db,
        organization_id=organization.id,
        target_membership=membership,
    )

    # Also remove workspace memberships held by this user inside the organization
    org_workspace_ids = list(
        db.scalars(select(Workspace.id).where(Workspace.organization_id == organization.id))
    )
    if org_workspace_ids:
        ws_memberships = list(
            db.scalars(
                select(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id.in_(org_workspace_ids),
                    WorkspaceMembership.user_id == membership.user_id,
                )
            )
        )
        for ws_mem in ws_memberships:
            db.delete(ws_mem)

    target_user = db.get(User, membership.user_id)
    revoked_count = revoke_user_sessions(
        db,
        user_id=membership.user_id,
        reason="ORGANIZATION_MEMBERSHIP_REMOVED",
    )

    record_audit_event(
        db,
        organization_id=organization.id,
        actor_user=actor,
        event_type="organization.membership_removed",
        entity_type="organization_membership",
        entity_id=membership.id,
        summary=(
            f"Removed organization membership for "
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


def create_organization_invitation(
    db: Session,
    *,
    organization: Organization,
    actor: User,
    payload: OrganizationInvitationCreateRequest,
    settings: Settings,
    ip_address: str | None,
) -> tuple[OrganizationInvitation, str]:
    """Create an anti-enumeration organization invitation without querying global Users."""
    _lock_organization_for_mutation(db, organization.id)
    now = utc_now()

    # Revoke any previously pending invitations for the same org + email cleanly
    db.execute(
        update(OrganizationInvitation)
        .where(
            OrganizationInvitation.organization_id == organization.id,
            OrganizationInvitation.invited_email == payload.email,
            OrganizationInvitation.accepted_at.is_(None),
            OrganizationInvitation.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )

    raw_token = secrets.token_urlsafe(32)
    invitation = OrganizationInvitation(
        organization_id=organization.id,
        invited_email=payload.email,
        role=payload.role,
        token_hash=hash_refresh_token(raw_token),
        invited_by_user_id=actor.id,
        expires_at=now + timedelta(hours=settings.invitation_expire_hours),
    )
    db.add(invitation)
    db.flush()

    record_audit_event(
        db,
        organization_id=organization.id,
        actor_user=actor,
        event_type="organization.invitation_created",
        entity_type="organization_invitation",
        entity_id=invitation.id,
        summary=f"Issued organization invitation with role {payload.role}.",
        tone="neutral",
        metadata={
            "invitationId": str(invitation.id),
            "role": payload.role,
        },
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(invitation)
    return invitation, raw_token


def list_organization_invitations(
    db: Session, *, organization_id: uuid.UUID
) -> list[OrganizationInvitation]:
    return list(
        db.scalars(
            select(OrganizationInvitation)
            .where(OrganizationInvitation.organization_id == organization_id)
            .order_by(OrganizationInvitation.created_at.desc())
        )
    )


def revoke_organization_invitation(
    db: Session,
    *,
    organization: Organization,
    invitation_id: uuid.UUID,
    actor: User,
    ip_address: str | None,
) -> None:
    invitation = db.scalar(
        select(OrganizationInvitation)
        .where(
            OrganizationInvitation.id == invitation_id,
            OrganizationInvitation.organization_id == organization.id,
        )
        .with_for_update()
    )
    if invitation is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="INVITATION_NOT_FOUND",
            message="Organization invitation was not found.",
        )

    if invitation.accepted_at is not None:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="INVITATION_ALREADY_ACCEPTED",
            message="Cannot revoke an invitation that has already been accepted.",
        )

    if invitation.revoked_at is None:
        invitation.revoked_at = utc_now()
        record_audit_event(
            db,
            organization_id=organization.id,
            actor_user=actor,
            event_type="organization.invitation_revoked",
            entity_type="organization_invitation",
            entity_id=invitation.id,
            summary="Revoked pending organization invitation.",
            tone="warning",
            metadata={"invitationId": str(invitation.id)},
            ip_address=ip_address,
        )
    db.commit()


def accept_organization_invitation(
    db: Session,
    *,
    raw_token: str,
    user: User,
    ip_address: str | None,
) -> tuple[Organization, OrganizationMembership]:
    token_hash = hash_refresh_token(raw_token)
    invitation = db.scalar(
        select(OrganizationInvitation)
        .where(OrganizationInvitation.token_hash == token_hash)
        .with_for_update()
    )
    if invitation is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="INVITATION_NOT_FOUND",
            message="Organization invitation is invalid.",
        )

    now = utc_now()
    if (
        invitation.revoked_at is not None
        or invitation.accepted_at is not None
        or _ensure_utc(invitation.expires_at) <= now
    ):
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="INVITATION_EXPIRED_OR_USED",
            message="Organization invitation has expired, been revoked, or already accepted.",
        )

    if user.email.strip().lower() != invitation.invited_email.strip().lower():
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="INVITATION_EMAIL_MISMATCH",
            message="Authenticated user email does not match the invitation email.",
        )

    _lock_organization_for_mutation(db, invitation.organization_id)
    organization = db.get(Organization, invitation.organization_id)
    if organization is None or not organization.is_active:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ORGANIZATION_NOT_FOUND",
            message="Organization not found.",
        )

    membership = db.scalar(
        select(OrganizationMembership)
        .where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == user.id,
        )
        .with_for_update()
    )
    if membership is None:
        membership = OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role=invitation.role,
            status="ACTIVE",
        )
        db.add(membership)
        db.flush()
    else:
        if membership.role != "ORG_OWNER":
            membership.role = invitation.role
        membership.status = "ACTIVE"

    invitation.accepted_at = now
    invitation.accepted_by_user_id = user.id

    record_audit_event(
        db,
        organization_id=organization.id,
        actor_user=user,
        event_type="organization.invitation_accepted",
        entity_type="organization_membership",
        entity_id=membership.id,
        summary=f"{user.full_name} accepted invitation and joined organization as {membership.role}.",
        tone="success",
        metadata={"invitationId": str(invitation.id), "role": membership.role},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(organization)
    db.refresh(membership)
    return organization, membership


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
        OrganizationMembership.status == "ACTIVE",
    ]
    if organization_id is not None:
        conditions.append(Workspace.organization_id == organization_id)

    rows = db.execute(
        select(Workspace, WorkspaceMembership)
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
        .join(Organization, Organization.id == Workspace.organization_id)
        .join(
            OrganizationMembership,
            (OrganizationMembership.organization_id == Organization.id)
            & (OrganizationMembership.user_id == user_id),
        )
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

    try:
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
            company_gstin=payload.company_gstin,
            company_pan=payload.company_pan,
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
    except IntegrityError as exc:
        db.rollback()
        if _get_constraint_name(exc) == "uq_workspaces_organization_id_workspace_code":
            raise AppError(
                status_code=status.HTTP_409_CONFLICT,
                code="WORKSPACE_CODE_EXISTS",
                message="A workspace with this code already exists in the organization.",
            ) from exc
        raise

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
        if field == "registered_address" and isinstance(value, str):
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
    # Deterministic lock ordering on parent Workspace before membership checks/insert
    _lock_workspace_for_mutation(db, workspace.id)

    # Enforce active membership within the parent Organization and return one uniform
    # error for non-members, suspended org members, and unknown platform emails to prevent
    # global cross-organization email enumeration.
    target_user = db.scalar(
        select(User)
        .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
        .where(
            func.lower(User.email) == payload.email.strip().lower(),
            User.is_active.is_(True),
            OrganizationMembership.organization_id == workspace.organization_id,
            OrganizationMembership.status == "ACTIVE",
        )
    )
    if target_user is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ORGANIZATION_MEMBER_NOT_FOUND",
            message="User is not an active member of this organization.",
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

    try:
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
    except IntegrityError as exc:
        db.rollback()
        if _get_constraint_name(exc) == "uq_workspace_memberships_workspace_id_user_id":
            raise AppError(
                status_code=status.HTTP_409_CONFLICT,
                code="MEMBERSHIP_ALREADY_EXISTS",
                message="User already holds a membership in this workspace.",
            ) from exc
        raise

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
            .order_by(WorkspaceMembership.id.asc())
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
    # Lock parent Workspace first to eliminate cross-row dual-admin FOR UPDATE deadlocks
    _lock_workspace_for_mutation(db, workspace.id)

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
    # Lock parent Workspace first to eliminate cross-row dual-admin FOR UPDATE deadlocks
    _lock_workspace_for_mutation(db, workspace.id)

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
