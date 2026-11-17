from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.cookies import (
    ACCESS_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    clear_auth_cookies,
    set_auth_cookies,
)
from app.core.deps import (
    AuthPrincipal,
    get_app_settings,
    get_client_ip,
    get_current_principal,
    require_allowed_origin,
    require_csrf,
)
from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MeResponse,
    OrganizationMembershipSummaryDto,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
    UserSummaryDto,
    WorkspaceMembershipSummaryDto,
)
from app.services.auth_service import (
    get_user_memberships_snapshot,
    login_user,
    logout_all_sessions,
    logout_session,
    refresh_user_session,
    register_user,
)
from app.services.rate_limit_service import enforce_auth_rate_limit

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_allowed_origin)],
    summary="Register a new user account and issue session cookies (Origin-validated, rate-limited)",
)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> RegisterResponse:
    client_ip = get_client_ip(request)
    enforce_auth_rate_limit(
        request,
        settings,
        action="register",
        ip_address=client_ip,
    )
    user, org_bundle, ws_bundle, issued = register_user(
        db,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        organization_name=payload.organization_name,
        firm_type=payload.firm_type,
        settings=settings,
        ip_address=client_ip,
        user_agent=request.headers.get("user-agent"),
    )
    set_auth_cookies(
        response,
        settings,
        access_token=issued.access_token,
        refresh_token=issued.refresh_token,
        csrf_token=issued.csrf_token,
    )

    org_dto = (
        OrganizationMembershipSummaryDto(
            id=org_bundle[0].id,
            name=org_bundle[0].name,
            slug=org_bundle[0].slug,
            firm_type=org_bundle[0].firm_type,
            role=org_bundle[1].role,  # type: ignore[arg-type]
        )
        if org_bundle is not None
        else None
    )
    ws_dto = (
        WorkspaceMembershipSummaryDto(
            workspace_id=ws_bundle[0].id,
            organization_id=ws_bundle[0].organization_id,
            name=ws_bundle[0].name,
            workspace_code=ws_bundle[0].workspace_code,
            role=ws_bundle[1].role,  # type: ignore[arg-type]
        )
        if ws_bundle is not None
        else None
    )

    return RegisterResponse(
        user=UserSummaryDto(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
        ),
        organization=org_dto,
        workspace=ws_dto,
        session_expires_at=issued.refresh_expires_at,
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    response_model_by_alias=True,
    dependencies=[Depends(require_allowed_origin)],
    summary="Authenticate via Argon2id and issue HttpOnly cookies (Origin-validated, rate-limited)",
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> LoginResponse:
    client_ip = get_client_ip(request)
    enforce_auth_rate_limit(
        request,
        settings,
        action="login",
        ip_address=client_ip,
        account_identifier=payload.email,
    )
    user, ws_rows, issued = login_user(
        db,
        email=payload.email,
        password=payload.password,
        settings=settings,
        ip_address=client_ip,
        user_agent=request.headers.get("user-agent"),
    )
    set_auth_cookies(
        response,
        settings,
        access_token=issued.access_token,
        refresh_token=issued.refresh_token,
        csrf_token=issued.csrf_token,
    )
    return LoginResponse(
        user=UserSummaryDto(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
        ),
        workspaces=[
            WorkspaceMembershipSummaryDto(
                workspace_id=ws.id,
                organization_id=ws.organization_id,
                name=ws.name,
                workspace_code=ws.workspace_code,
                role=membership.role,  # type: ignore[arg-type]
            )
            for ws, membership in ws_rows
        ],
        session_expires_at=issued.refresh_expires_at,
    )


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    response_model_by_alias=True,
    dependencies=[Depends(require_csrf)],
    summary="Rotate refresh cookie with token-family reuse detection and rate limiting",
)
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> RefreshResponse:
    client_ip = get_client_ip(request)
    enforce_auth_rate_limit(
        request,
        settings,
        action="refresh",
        ip_address=client_ip,
    )
    issued = refresh_user_session(
        db,
        raw_refresh_token=request.cookies.get(REFRESH_COOKIE_NAME),
        settings=settings,
        ip_address=client_ip,
        user_agent=request.headers.get("user-agent"),
    )
    set_auth_cookies(
        response,
        settings,
        access_token=issued.access_token,
        refresh_token=issued.refresh_token,
        csrf_token=issued.csrf_token,
    )
    return RefreshResponse(
        refreshed=True,
        session_expires_at=issued.refresh_expires_at,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    summary="Revoke current session and clear auth/CSRF cookies",
)
def logout(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> Response:
    logout_session(
        db,
        raw_access_token=request.cookies.get(ACCESS_COOKIE_NAME),
        raw_refresh_token=request.cookies.get(REFRESH_COOKIE_NAME),
        settings=settings,
        ip_address=get_client_ip(request),
    )
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(response, settings)
    return response


@router.post(
    "/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    summary="Revoke all sessions for the authenticated user and clear local cookies",
)
def logout_all(
    request: Request,
    principal: AuthPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> Response:
    logout_all_sessions(
        db,
        user=principal.user,
        ip_address=get_client_ip(request),
    )
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(response, settings)
    return response


@router.get(
    "/me",
    response_model=MeResponse,
    response_model_by_alias=True,
    summary="Return current authenticated user profile and active memberships",
)
def me(
    principal: AuthPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> MeResponse:
    org_rows, ws_rows = get_user_memberships_snapshot(db, principal.user.id)
    return MeResponse(
        user=UserSummaryDto(
            id=principal.user.id,
            email=principal.user.email,
            full_name=principal.user.full_name,
            is_active=principal.user.is_active,
        ),
        organizations=[
            OrganizationMembershipSummaryDto(
                id=org.id,
                name=org.name,
                slug=org.slug,
                firm_type=org.firm_type,
                role=membership.role,  # type: ignore[arg-type]
            )
            for org, membership in org_rows
        ],
        workspaces=[
            WorkspaceMembershipSummaryDto(
                workspace_id=ws.id,
                organization_id=ws.organization_id,
                name=ws.name,
                workspace_code=ws.workspace_code,
                role=membership.role,  # type: ignore[arg-type]
            )
            for ws, membership in ws_rows
        ],
    )
