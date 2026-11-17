from __future__ import annotations

from urllib.parse import urlparse

from fastapi import Request, Response

from app.core.config import Settings

ACCESS_COOKIE_NAME = "norus_access_token"
REFRESH_COOKIE_NAME = "norus_refresh_token"
CSRF_COOKIE_NAME = "norus_csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"


def set_auth_cookies(
    response: Response,
    settings: Settings,
    *,
    access_token: str,
    refresh_token: str,
    csrf_token: str,
) -> None:
    """Attach HttpOnly access/refresh cookies and readable double-submit CSRF cookie."""
    api_prefix = settings.api_v1_prefix.rstrip("/") or "/api/v1"
    access_max_age = settings.access_token_expire_minutes * 60
    refresh_max_age = settings.refresh_token_expire_days * 86400

    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=access_token,
        max_age=access_max_age,
        path=api_prefix,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=refresh_max_age,
        path=f"{api_prefix}/auth",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=refresh_max_age,
        path="/",
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
    )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    """Expire access, refresh, and CSRF cookies across their exact issuance paths."""
    api_prefix = settings.api_v1_prefix.rstrip("/") or "/api/v1"
    response.delete_cookie(
        key=ACCESS_COOKIE_NAME,
        path=api_prefix,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=f"{api_prefix}/auth",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        path="/",
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
    )


def extract_normalized_origin(raw_url: str) -> str | None:
    """Normalize an Origin or Referer URL to scheme://netloc for allowlist comparison."""
    cleaned = raw_url.strip()
    if not cleaned:
        return None
    parsed = urlparse(cleaned)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def is_allowed_request_origin(request: Request, settings: Settings) -> bool:
    """Validate Origin or Referer against explicit configured CORS_ORIGINS."""
    allowed = {
        normalized
        for origin in settings.cors_origins
        if (normalized := extract_normalized_origin(origin)) is not None
    }

    origin_header = request.headers.get("origin")
    if origin_header is not None:
        normalized_origin = extract_normalized_origin(origin_header)
        return normalized_origin is not None and normalized_origin in allowed

    referer_header = request.headers.get("referer")
    if referer_header is not None:
        normalized_referer = extract_normalized_origin(referer_header)
        return normalized_referer is not None and normalized_referer in allowed

    # Browsers always send Origin on unsafe requests; non-browser HTTP test clients
    # in dev/test omit Origin unless explicitly supplied. Reject missing Origin/Referer
    # in staging/production.
    return settings.app_env not in {"staging", "production"}
