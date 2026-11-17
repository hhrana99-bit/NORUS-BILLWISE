from __future__ import annotations

import ipaddress
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, Path, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.cookies import (
    ACCESS_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    is_allowed_request_origin,
)
from app.core.errors import AppError
from app.core.security import constant_time_equals
from app.db.session import get_db
from app.models.tenancy import (
    Organization,
    OrganizationMembership,
    User,
    UserSession,
    Workspace,
    WorkspaceMembership,
)
from app.services.auth_service import validate_access_session


@dataclass(frozen=True)
class AuthPrincipal:
    user: User
    session: UserSession
    organization_id: uuid.UUID | None


@dataclass(frozen=True)
class OrganizationContext:
    organization: Organization
    membership: OrganizationMembership
    principal: AuthPrincipal


@dataclass(frozen=True)
class WorkspaceContext:
    workspace: Workspace
    membership: WorkspaceMembership
    organization_membership: OrganizationMembership
    principal: AuthPrincipal


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def _parse_ip(raw_value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    cleaned = raw_value.strip()
    if not cleaned:
        return None
    try:
        return ipaddress.ip_address(cleaned)
    except ValueError:
        return None


def _is_trusted_proxy_ip(
    ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address,
    trusted_networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network],
) -> bool:
    return any(ip_obj in net for net in trusted_networks)


def get_client_ip(request: Request, settings: Settings | None = None) -> str | None:
    """Resolve client IP, trusting X-Forwarded-For ONLY when direct peer matches trusted_proxies."""
    if request.client is None or not request.client.host:
        return None

    direct_host = request.client.host.strip()
    if not direct_host:
        return None

    active_settings = settings
    if active_settings is None:
        app = request.scope.get("app")
        if app is not None and hasattr(app, "state"):
            active_settings = getattr(app.state, "settings", None)

    trusted_entries = active_settings.trusted_proxies if active_settings is not None else []
    if not trusted_entries:
        return direct_host

    direct_ip = _parse_ip(direct_host)
    if direct_ip is None:
        return direct_host

    trusted_networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for entry in trusted_entries:
        try:
            trusted_networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            continue

    if not trusted_networks or not _is_trusted_proxy_ip(direct_ip, trusted_networks):
        return str(direct_ip)

    xff_values = request.headers.getlist("x-forwarded-for")
    if not xff_values:
        return str(direct_ip)

    raw_hops = [
        hop.strip()
        for header_val in xff_values
        for hop in header_val.split(",")
        if hop.strip()
    ]
    if not raw_hops:
        return str(direct_ip)

    last_trusted_valid_ip = str(direct_ip)
    for raw_hop in reversed(raw_hops):
        hop_ip = _parse_ip(raw_hop)
        if hop_ip is None:
            return last_trusted_valid_ip
        if _is_trusted_proxy_ip(hop_ip, trusted_networks):
            last_trusted_valid_ip = str(hop_ip)
            continue
        return str(hop_ip)

    return last_trusted_valid_ip


def require_allowed_origin(
    request: Request,
    settings: Settings = Depends(get_app_settings),
) -> None:
    """Enforce configured Origin/Referer allowlist (blocks Login/Register CSRF without CSRF token)."""
    if not is_allowed_request_origin(request, settings):
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="CSRF_TOKEN_INVALID",
            message="Request origin is not permitted.",
        )


def require_csrf(
    request: Request,
    settings: Settings = Depends(get_app_settings),
) -> None:
    """Validate Origin/Referer allowlist and double-submit CSRF cookie vs X-CSRF-Token header."""
    require_allowed_origin(request, settings)

    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    header_token = request.headers.get(CSRF_HEADER_NAME)
    if not constant_time_equals(cookie_token, header_token):
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="CSRF_TOKEN_INVALID",
            message="Missing or invalid CSRF token.",
        )


def get_current_principal(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> AuthPrincipal:
    """Authenticate caller exclusively via verified access cookie and active UserSession."""
    raw_access_token = request.cookies.get(ACCESS_COOKIE_NAME)
    user, session, org_id = validate_access_session(
        db,
        raw_access_token=raw_access_token,
        settings=settings,
    )
    return AuthPrincipal(user=user, session=session, organization_id=org_id)


def require_organization_role(
    *allowed_roles: str,
) -> Callable[..., OrganizationContext]:
    """Dependency factory enforcing active OrganizationMembership and explicit org role."""

    def _dependency(
        organization_id: uuid.UUID = Path(..., alias="organizationId"),
        principal: AuthPrincipal = Depends(get_current_principal),
        db: Session = Depends(get_db),
    ) -> OrganizationContext:
        row = db.execute(
            select(Organization, OrganizationMembership)
            .join(
                OrganizationMembership,
                OrganizationMembership.organization_id == Organization.id,
            )
            .where(
                Organization.id == organization_id,
                Organization.is_active.is_(True),
                OrganizationMembership.user_id == principal.user.id,
                OrganizationMembership.status == "ACTIVE",
            )
        ).first()
        if row is None:
            raise AppError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="ORGANIZATION_NOT_FOUND",
                message="Organization not found.",
            )

        organization, membership = row[0], row[1]
        if allowed_roles and membership.role not in allowed_roles:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                code="FORBIDDEN_ROLE",
                message="You do not have permission to perform this organization action.",
            )
        return OrganizationContext(
            organization=organization,
            membership=membership,
            principal=principal,
        )

    return _dependency


def require_workspace_role(
    *allowed_roles: str,
) -> Callable[..., WorkspaceContext]:
    """Dependency factory enforcing active org + workspace memberships and explicit workspace role."""

    def _dependency(
        workspace_id: uuid.UUID = Path(..., alias="workspaceId"),
        principal: AuthPrincipal = Depends(get_current_principal),
        db: Session = Depends(get_db),
    ) -> WorkspaceContext:
        row = db.execute(
            select(Workspace, WorkspaceMembership, OrganizationMembership)
            .join(
                WorkspaceMembership,
                WorkspaceMembership.workspace_id == Workspace.id,
            )
            .join(Organization, Organization.id == Workspace.organization_id)
            .join(
                OrganizationMembership,
                (OrganizationMembership.organization_id == Organization.id)
                & (OrganizationMembership.user_id == principal.user.id),
            )
            .where(
                Workspace.id == workspace_id,
                Workspace.is_active.is_(True),
                Organization.is_active.is_(True),
                WorkspaceMembership.user_id == principal.user.id,
                WorkspaceMembership.status == "ACTIVE",
                OrganizationMembership.status == "ACTIVE",
            )
        ).first()
        if row is None:
            raise AppError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="WORKSPACE_NOT_FOUND",
                message="Workspace not found.",
            )

        workspace, ws_membership, org_membership = row[0], row[1], row[2]
        if allowed_roles and ws_membership.role not in allowed_roles:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                code="FORBIDDEN_ROLE",
                message="You do not have permission to perform this workspace action.",
            )
        return WorkspaceContext(
            workspace=workspace,
            membership=ws_membership,
            organization_membership=org_membership,
            principal=principal,
        )

    return _dependency
