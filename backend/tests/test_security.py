from __future__ import annotations

import uuid
from datetime import timedelta

import jwt
import pytest

from app.core.config import Settings
from app.core.security import (
    JWT_ALGORITHM,
    TokenValidationError,
    constant_time_equals,
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


def _security_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+psycopg://postgres:test_only@localhost:5432/norus_billwise_test",
        jwt_secret_key="unit-test-only-signing-secret-with-32-plus-chars",
        cookie_secure=False,
        cors_origins=["http://localhost:3000"],
        access_token_expire_minutes=15,
        refresh_token_expire_days=14,
        jwt_issuer="norus-billwise-api",
        jwt_audience="norus-billwise-app",
    )


def test_argon2id_hashing_salts_and_verifies() -> None:
    password = "StrongPracticePassword!2026"
    hash_one = hash_password(password)
    hash_two = hash_password(password)

    assert hash_one.startswith("$argon2id$")
    assert "m=65536,t=3,p=4" in hash_one
    assert hash_one != hash_two
    assert verify_password(hash_one, password) is True
    assert verify_password(hash_one, "WrongPassword!2026") is False
    assert verify_password("not-a-valid-phc-hash", password) is False
    assert password_needs_rehash(hash_one) is False

    # Dummy verification runs constant-work verification path without raising
    dummy_verify_password(password)


def test_hash_password_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="empty"):
        hash_password("")


def test_refresh_token_generation_and_sha256_hashing() -> None:
    raw_one = generate_refresh_token()
    raw_two = generate_refresh_token()

    assert len(raw_one) >= 48
    assert raw_one != raw_two

    digest = hash_refresh_token(raw_one)
    assert len(digest) == 64
    assert digest != raw_one
    assert digest == hash_refresh_token(raw_one)
    assert digest != hash_refresh_token(raw_two)

    with pytest.raises(ValueError, match="empty"):
        hash_refresh_token("")


def test_csrf_token_generation_and_constant_time_comparison() -> None:
    token = generate_csrf_token()
    assert len(token) >= 32
    assert constant_time_equals(token, token) is True
    assert constant_time_equals(token, f"{token}-tampered") is False
    assert constant_time_equals(token, None) is False
    assert constant_time_equals(None, token) is False
    assert constant_time_equals("", "") is False


def test_access_jwt_claims_and_verification() -> None:
    settings = _security_settings()
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    org_id = uuid.uuid4()

    token, expires_at = create_access_token(
        user_id=user_id,
        session_id=session_id,
        organization_id=org_id,
        settings=settings,
    )
    assert expires_at is not None

    claims = decode_access_token(token, settings)
    assert claims["sub"] == str(user_id)
    assert claims["sid"] == str(session_id)
    assert claims["org_id"] == str(org_id)
    assert claims["typ"] == "access"
    assert claims["iss"] == settings.jwt_issuer
    assert claims["aud"] == settings.jwt_audience
    assert uuid.UUID(claims["jti"])


def test_access_jwt_rejects_expired_tampered_and_wrong_claim_tokens() -> None:
    settings = _security_settings()
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()

    expired_token, _ = create_access_token(
        user_id=user_id,
        session_id=session_id,
        organization_id=None,
        settings=settings,
        expires_delta=timedelta(seconds=-10),
    )
    with pytest.raises(TokenValidationError):
        decode_access_token(expired_token, settings)

    valid_token, _ = create_access_token(
        user_id=user_id,
        session_id=session_id,
        organization_id=None,
        settings=settings,
    )
    tampered_token = f"{valid_token[:-4]}aaaa"
    with pytest.raises(TokenValidationError):
        decode_access_token(tampered_token, settings)

    wrong_secret_token = jwt.encode(
        {
            "sub": str(user_id),
            "sid": str(session_id),
            "org_id": None,
            "jti": str(uuid.uuid4()),
            "typ": "access",
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": 1700000000,
            "exp": 4102444800,
        },
        "completely-different-secret-key-at-least-32-chars",
        algorithm=JWT_ALGORITHM,
    )
    with pytest.raises(TokenValidationError):
        decode_access_token(wrong_secret_token, settings)

    wrong_type_token = jwt.encode(
        {
            "sub": str(user_id),
            "sid": str(session_id),
            "org_id": None,
            "jti": str(uuid.uuid4()),
            "typ": "refresh",
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": 1700000000,
            "exp": 4102444800,
        },
        settings.jwt_secret_key.get_secret_value(),
        algorithm=JWT_ALGORITHM,
    )
    with pytest.raises(TokenValidationError):
        decode_access_token(wrong_type_token, settings)


def test_origin_normalization_and_schema_human_review_guard() -> None:
    from pydantic import ValidationError

    from app.core.cookies import extract_normalized_origin
    from app.schemas.auth import RegisterRequest
    from app.schemas.tenancy import (
        WorkspaceCreateRequest,
        WorkspaceSettingsUpdateRequest,
    )

    assert (
        extract_normalized_origin("https://App.Norus.Example:8443/login?next=/")
        == "https://app.norus.example:8443"
    )
    assert extract_normalized_origin("relative/path") is None

    with pytest.raises(ValidationError):
        RegisterRequest(
            email="valid@example.com",
            password="            ",
            full_name="Test User",
        )

    with pytest.raises(ValidationError, match="HUMAN_REVIEW_CANNOT_BE_DISABLED"):
        WorkspaceCreateRequest(
            name="Client",
            workspace_code="WS-01",
            legal_entity_name="Client LLP",
            require_human_review=False,
        )

    with pytest.raises(ValidationError, match="HUMAN_REVIEW_CANNOT_BE_DISABLED"):
        WorkspaceSettingsUpdateRequest(require_human_review=False)

