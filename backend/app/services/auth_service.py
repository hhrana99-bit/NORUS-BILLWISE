from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import (
    TokenValidationError,
    create_access_token,
    decode_access_token,
    dummy_verify_password,
    generate_csrf_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    password_needs_rehash,
    verify_password,
)
from app.models.tenancy import (
    Organization,
    OrganizationMembership,
    User,
    UserSession,
    Workspace,
    WorkspaceMembership,
    WorkspaceSettings,
    utc_now,
)
from app.services.audit_service import record_audit_event


@dataclass(frozen=True)
class IssuedSessionTokens:
    access_token: str
    refresh_token: str
    csrf_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime
    session: UserSession


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _get_constraint_name(exc: IntegrityError) -> str | None:
    return getattr(getattr(exc.orig, "diag", None), "constraint_name", None)


def generate_unique_org_slug(db: Session, org_name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", org_name.strip().lower()).strip("-")
    base = (base[:80] or "organization").strip("-")
    existing = db.scalar(select(Organization.id).where(Organization.slug == base))
    if existing is None:
        return base
    for _ in range(8):
        candidate = f"{base[:72]}-{secrets.token_hex(3)}"
        if db.scalar(select(Organization.id).where(Organization.slug == candidate)) is None:
            return candidate
    return f"{base[:64]}-{uuid.uuid4().hex[:12]}"


def get_primary_active_organization_id(db: Session, user_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(
        select(OrganizationMembership.organization_id)
        .join(Organization, Organization.id == OrganizationMembership.organization_id)
        .where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.status == "ACTIVE",
            Organization.is_active.is_(True),
        )
        .order_by(OrganizationMembership.created_at.asc())
        .limit(1)
    )


def get_active_organization_ids(db: Session, user_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(OrganizationMembership.organization_id)
            .join(Organization, Organization.id == OrganizationMembership.organization_id)
            .where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.status == "ACTIVE",
                Organization.is_active.is_(True),
            )
            .order_by(OrganizationMembership.created_at.asc())
        )
    )


def get_user_memberships_snapshot(
    db: Session, user_id: uuid.UUID
) -> tuple[list[tuple[Organization, OrganizationMembership]], list[tuple[Workspace, WorkspaceMembership]]]:
    org_rows = list(
        db.execute(
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
    )
    ws_rows = list(
        db.execute(
            select(Workspace, WorkspaceMembership)
            .join(
                WorkspaceMembership,
                WorkspaceMembership.workspace_id == Workspace.id,
            )
            .join(Organization, Organization.id == Workspace.organization_id)
            .join(
                OrganizationMembership,
                (OrganizationMembership.organization_id == Organization.id)
                & (OrganizationMembership.user_id == user_id),
            )
            .where(
                WorkspaceMembership.user_id == user_id,
                WorkspaceMembership.status == "ACTIVE",
                Workspace.is_active.is_(True),
                Organization.is_active.is_(True),
                OrganizationMembership.status == "ACTIVE",
            )
            .order_by(Workspace.created_at.asc())
        ).all()
    )
    return [(row[0], row[1]) for row in org_rows], [(row[0], row[1]) for row in ws_rows]


def revoke_user_sessions(
    db: Session,
    *,
    user_id: uuid.UUID,
    reason: str,
) -> int:
    """Immediately revoke all active (unrevoked) sessions for a given user."""
    now = utc_now()
    result = db.execute(
        update(UserSession)
        .where(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
        )
        .values(revoked_at=now, revoke_reason=reason)
    )
    return int(result.rowcount or 0)


def _issue_new_session(
    db: Session,
    *,
    user: User,
    organization_id: uuid.UUID | None,
    settings: Settings,
    ip_address: str | None,
    user_agent: str | None,
    token_family_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
) -> IssuedSessionTokens:
    now = utc_now()
    sid = session_id or uuid.uuid4()
    family_id = token_family_id or uuid.uuid4()
    raw_refresh = generate_refresh_token()
    refresh_hash = hash_refresh_token(raw_refresh)
    refresh_expires_at = now + timedelta(days=settings.refresh_token_expire_days)

    user_session = UserSession(
        id=sid,
        user_id=user.id,
        token_family_id=family_id,
        refresh_token_hash=refresh_hash,
        ip_address=(ip_address or "")[:64] or None,
        user_agent=(user_agent or "")[:512] or None,
        expires_at=refresh_expires_at,
    )
    db.add(user_session)
    db.flush()

    access_token, access_expires_at = create_access_token(
        user_id=user.id,
        session_id=sid,
        organization_id=organization_id,
        settings=settings,
    )
    csrf_token = generate_csrf_token()
    return IssuedSessionTokens(
        access_token=access_token,
        refresh_token=raw_refresh,
        csrf_token=csrf_token,
        access_expires_at=access_expires_at,
        refresh_expires_at=refresh_expires_at,
        session=user_session,
    )


def register_user(
    db: Session,
    *,
    email: str,
    password: str,
    full_name: str,
    organization_name: str | None,
    firm_type: str,
    settings: Settings,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[
    User,
    tuple[Organization, OrganizationMembership] | None,
    tuple[Workspace, WorkspaceMembership] | None,
    IssuedSessionTokens,
]:
    normalized_email = email.strip().lower()
    existing_user = db.scalar(
        select(User.id).where(func.lower(User.email) == normalized_email)
    )
    if existing_user is not None:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="EMAIL_ALREADY_EXISTS",
            message="An account with this email address already exists.",
        )

    password_hash = hash_password(password)

    try:
        user = User(
            email=normalized_email,
            full_name=full_name.strip(),
            password_hash=password_hash,
            is_active=True,
            last_login_at=utc_now(),
        )
        db.add(user)
        db.flush()

        org_bundle: tuple[Organization, OrganizationMembership] | None = None
        ws_bundle: tuple[Workspace, WorkspaceMembership] | None = None
        primary_org_id: uuid.UUID | None = None

        if organization_name:
            clean_org_name = organization_name.strip()
            org = Organization(
                name=clean_org_name,
                slug=generate_unique_org_slug(db, clean_org_name),
                firm_type=firm_type.strip(),
                primary_contact_email=normalized_email,
                is_active=True,
            )
            db.add(org)
            db.flush()

            org_membership = OrganizationMembership(
                organization_id=org.id,
                user_id=user.id,
                role="ORG_OWNER",
                status="ACTIVE",
            )
            db.add(org_membership)

            workspace = Workspace(
                organization_id=org.id,
                name=clean_org_name,
                workspace_code="WS-DEFAULT-001",
                is_active=True,
            )
            db.add(workspace)
            db.flush()

            ws_settings = WorkspaceSettings(
                workspace_id=workspace.id,
                legal_entity_name=clean_org_name,
                require_human_review=True,
            )
            db.add(ws_settings)

            ws_membership = WorkspaceMembership(
                workspace_id=workspace.id,
                user_id=user.id,
                role="WORKSPACE_ADMIN",
                status="ACTIVE",
                invited_by_user_id=user.id,
            )
            db.add(ws_membership)
            db.flush()

            primary_org_id = org.id
            org_bundle = (org, org_membership)
            ws_bundle = (workspace, ws_membership)

        issued = _issue_new_session(
            db,
            user=user,
            organization_id=primary_org_id,
            settings=settings,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        if primary_org_id is not None and ws_bundle is not None:
            record_audit_event(
                db,
                organization_id=primary_org_id,
                workspace_id=ws_bundle[0].id,
                actor_user=user,
                event_type="auth.register",
                entity_type="workspace",
                entity_id=ws_bundle[0].id,
                summary="Registered new account and provisioned initial organization and workspace.",
                tone="success",
                metadata={"sessionId": str(issued.session.id)},
                ip_address=ip_address,
            )

        db.commit()
    except IntegrityError as exc:
        db.rollback()
        constraint_name = _get_constraint_name(exc)
        if constraint_name == "uq_users_email_lower":
            raise AppError(
                status_code=status.HTTP_409_CONFLICT,
                code="EMAIL_ALREADY_EXISTS",
                message="An account with this email address already exists.",
            ) from exc
        if constraint_name == "uq_organizations_slug":
            raise AppError(
                status_code=status.HTTP_409_CONFLICT,
                code="ORGANIZATION_SLUG_CONFLICT",
                message="Organization slug collision; please retry registration.",
            ) from exc
        raise

    return user, org_bundle, ws_bundle, issued


def login_user(
    db: Session,
    *,
    email: str,
    password: str,
    settings: Settings,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[User, list[tuple[Workspace, WorkspaceMembership]], IssuedSessionTokens]:
    normalized_email = email.strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == normalized_email))
    if user is None:
        dummy_verify_password(password)
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="INVALID_CREDENTIALS",
            message="Invalid email or password.",
        )

    if not verify_password(user.password_hash, password):
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="INVALID_CREDENTIALS",
            message="Invalid email or password.",
        )

    if not user.is_active:
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="ACCOUNT_DISABLED",
            message="User account is disabled.",
        )

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    user.last_login_at = utc_now()

    primary_org_id = get_primary_active_organization_id(db, user.id)
    issued = _issue_new_session(
        db,
        user=user,
        organization_id=primary_org_id,
        settings=settings,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    org_rows, ws_rows = get_user_memberships_snapshot(db, user.id)
    # Record auth.login strictly at organization scope (workspace_id=None) so unrelated
    # workspace members do not observe another user's login metadata.
    for org, _ in org_rows:
        record_audit_event(
            db,
            organization_id=org.id,
            workspace_id=None,
            actor_user=user,
            event_type="auth.login",
            entity_type="session",
            entity_id=issued.session.id,
            summary="User authenticated via cookie session.",
            tone="neutral",
            metadata={"sessionId": str(issued.session.id)},
            ip_address=ip_address,
        )

    db.commit()
    return user, ws_rows, issued


def refresh_user_session(
    db: Session,
    *,
    raw_refresh_token: str | None,
    settings: Settings,
    ip_address: str | None,
    user_agent: str | None,
) -> IssuedSessionTokens:
    if not raw_refresh_token:
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="SESSION_EXPIRED_OR_REVOKED",
            message="Refresh session is missing, expired, or revoked.",
            clear_auth_cookies=True,
        )

    token_hash = hash_refresh_token(raw_refresh_token)
    session = db.scalar(
        select(UserSession)
        .where(UserSession.refresh_token_hash == token_hash)
        .with_for_update()
    )
    if session is None:
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="SESSION_EXPIRED_OR_REVOKED",
            message="Refresh session is invalid or revoked.",
            clear_auth_cookies=True,
        )

    user = db.get(User, session.user_id)
    now = utc_now()

    # Detect replay of a previously rotated refresh token and revoke the entire token family
    if (
        session.rotated_at is not None
        or session.replaced_by_session_id is not None
        or (session.revoked_at is not None and session.revoke_reason == "ROTATION")
    ):
        db.execute(
            update(UserSession)
            .where(
                UserSession.token_family_id == session.token_family_id,
                UserSession.revoked_at.is_(None),
            )
            .values(
                revoked_at=now,
                revoke_reason="REFRESH_TOKEN_REUSE_DETECTED",
            )
        )
        if user is not None:
            for org_id in get_active_organization_ids(db, user.id):
                record_audit_event(
                    db,
                    organization_id=org_id,
                    actor_user=user,
                    event_type="auth.refresh_reuse_detected",
                    entity_type="session",
                    entity_id=session.token_family_id,
                    summary="Detected rotated refresh token replay; revoked entire token family.",
                    tone="warning",
                    metadata={"tokenFamilyId": str(session.token_family_id)},
                    ip_address=ip_address,
                )
        db.commit()
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="SESSION_EXPIRED_OR_REVOKED",
            message="Refresh token replay detected; session family revoked.",
            clear_auth_cookies=True,
        )

    if (
        session.revoked_at is not None
        or _ensure_utc(session.expires_at) <= now
        or user is None
        or not user.is_active
    ):
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="SESSION_EXPIRED_OR_REVOKED",
            message="Session has expired or been revoked.",
            clear_auth_cookies=True,
        )

    replacement_session_id = uuid.uuid4()
    primary_org_id = get_primary_active_organization_id(db, user.id)
    issued = _issue_new_session(
        db,
        user=user,
        organization_id=primary_org_id,
        settings=settings,
        ip_address=ip_address,
        user_agent=user_agent,
        token_family_id=session.token_family_id,
        session_id=replacement_session_id,
    )

    session.rotated_at = now
    session.revoked_at = now
    session.revoke_reason = "ROTATION"
    session.replaced_by_session_id = issued.session.id

    db.commit()
    return issued


def logout_session(
    db: Session,
    *,
    raw_access_token: str | None,
    raw_refresh_token: str | None,
    settings: Settings,
    ip_address: str | None,
) -> None:
    session: UserSession | None = None

    if raw_access_token:
        try:
            payload = decode_access_token(raw_access_token, settings)
            sid = uuid.UUID(str(payload["sid"]))
            session = db.get(UserSession, sid)
        except (TokenValidationError, ValueError):
            session = None

    if session is None and raw_refresh_token:
        token_hash = hash_refresh_token(raw_refresh_token)
        session = db.scalar(
            select(UserSession).where(UserSession.refresh_token_hash == token_hash)
        )

    if session is None:
        return

    now = utc_now()
    if session.revoked_at is None:
        session.revoked_at = now
        session.revoke_reason = "USER_LOGOUT"
        user = db.get(User, session.user_id)
        if user is not None:
            for org_id in get_active_organization_ids(db, user.id):
                record_audit_event(
                    db,
                    organization_id=org_id,
                    actor_user=user,
                    event_type="auth.logout",
                    entity_type="session",
                    entity_id=session.id,
                    summary="User logged out current session.",
                    tone="neutral",
                    metadata={"sessionId": str(session.id)},
                    ip_address=ip_address,
                )
    db.commit()


def logout_all_sessions(
    db: Session,
    *,
    user: User,
    ip_address: str | None,
) -> None:
    revoke_user_sessions(db, user_id=user.id, reason="LOGOUT_ALL")
    for org_id in get_active_organization_ids(db, user.id):
        record_audit_event(
            db,
            organization_id=org_id,
            actor_user=user,
            event_type="auth.logout_all",
            entity_type="user",
            entity_id=user.id,
            summary="User revoked all active sessions across devices.",
            tone="neutral",
            ip_address=ip_address,
        )
    db.commit()


def validate_access_session(
    db: Session,
    *,
    raw_access_token: str | None,
    settings: Settings,
) -> tuple[User, UserSession, uuid.UUID | None]:
    """Validate access JWT signature, expiry, sid claim, and active server-side session."""
    if not raw_access_token:
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHORIZED",
            message="Authentication credentials were not provided.",
        )

    try:
        payload = decode_access_token(raw_access_token, settings)
        user_id = uuid.UUID(str(payload["sub"]))
        session_id = uuid.UUID(str(payload["sid"]))
        raw_org_id = payload.get("org_id")
        org_id = uuid.UUID(str(raw_org_id)) if raw_org_id is not None else None
    except (TokenValidationError, ValueError) as exc:
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="SESSION_EXPIRED_OR_REVOKED",
            message="Invalid or expired access token.",
        ) from exc

    session = db.get(UserSession, session_id)
    now = utc_now()
    if (
        session is None
        or session.user_id != user_id
        or session.revoked_at is not None
        or session.rotated_at is not None
        or _ensure_utc(session.expires_at) <= now
    ):
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="SESSION_EXPIRED_OR_REVOKED",
            message="Session has been revoked or expired.",
        )

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="ACCOUNT_DISABLED",
            message="User account is inactive or unavailable.",
        )

    return user, session, org_id
