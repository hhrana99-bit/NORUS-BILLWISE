from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings

JWT_ALGORITHM = "HS256"

# Explicit Argon2id parameters aligned with docs/BACKEND_ARCHITECTURE.md Section 6
_PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)

# Pre-computed dummy hash target used to avoid user-enumeration timing leaks on missing accounts
_DUMMY_ARGON2_HASH = _PASSWORD_HASHER.hash("norus-constant-time-dummy-password-do-not-use")


class TokenValidationError(ValueError):
    """Raised when an access JWT is missing, expired, malformed, or fails signature validation."""


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using Argon2id with per-user random salt."""
    if not plain_password:
        raise ValueError("Password cannot be empty.")
    return _PASSWORD_HASHER.hash(plain_password)


def verify_password(password_hash: str, plain_password: str) -> bool:
    """Verify a plaintext password against a stored Argon2id PHC hash."""
    if not password_hash or not plain_password:
        return False
    try:
        return bool(_PASSWORD_HASHER.verify(password_hash, plain_password))
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False


def dummy_verify_password(plain_password: str) -> None:
    """Run Argon2id verification against a fixed dummy hash when a login email is unknown."""
    try:
        _PASSWORD_HASHER.verify(_DUMMY_ARGON2_HASH, plain_password or "x")
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return


def password_needs_rehash(password_hash: str) -> bool:
    """Return True if an existing Argon2id hash should be upgraded to current parameters."""
    try:
        return bool(_PASSWORD_HASHER.check_needs_rehash(password_hash))
    except (InvalidHashError, VerificationError):
        return False


def generate_refresh_token() -> str:
    """Generate a high-entropy CSPRNG opaque refresh token (never stored in plaintext)."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(raw_token: str) -> str:
    """Compute the SHA-256 hex digest of an opaque refresh token for database storage."""
    if not raw_token:
        raise ValueError("Refresh token cannot be empty.")
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_csrf_token() -> str:
    """Generate a cryptographically random double-submit CSRF token."""
    return secrets.token_urlsafe(32)


def constant_time_equals(left: str | None, right: str | None) -> bool:
    """Compare two secrets/tokens in constant time."""
    if not left or not right:
        return False
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def create_access_token(
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    organization_id: uuid.UUID | None,
    settings: Settings,
    expires_delta: timedelta | None = None,
) -> tuple[str, datetime]:
    """Sign a short-lived HS256 JWT carrying user, session (sid), and organization claims."""
    now = datetime.now(timezone.utc)
    ttl = expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    expires_at = now + ttl
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "sid": str(session_id),
        "org_id": str(organization_id) if organization_id is not None else None,
        "jti": str(uuid.uuid4()),
        "typ": "access",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    encoded = jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=JWT_ALGORITHM,
    )
    return encoded, expires_at


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    """Decode and strictly verify an access JWT without trusting token-header algorithms."""
    if not token:
        raise TokenValidationError("Missing access token.")
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "sid", "jti", "iat", "exp"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenValidationError("Invalid or expired access token.") from exc

    if payload.get("typ") != "access" or "org_id" not in payload:
        raise TokenValidationError("Invalid access token claims.")

    return payload
