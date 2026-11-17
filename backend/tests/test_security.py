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
    from decimal import Decimal

    from pydantic import ValidationError

    from app.core.cookies import extract_normalized_origin
    from app.schemas.auth import LoginRequest, RegisterRequest
    from app.schemas.tenancy import (
        OrganizationInvitationCreateRequest,
        WorkspaceCreateRequest,
        WorkspaceSettingsUpdateRequest,
    )

    assert (
        extract_normalized_origin("https://App.Norus.Example:8443/login?next=/")
        == "https://app.norus.example:8443"
    )
    assert extract_normalized_origin("relative/path") is None

    # All-whitespace AND padded-short passwords must be rejected (< 12 non-whitespace chars)
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="valid@example.com",
            password="            ",
            full_name="Test User",
        )
    with pytest.raises(ValidationError, match="non-whitespace"):
        RegisterRequest(
            email="valid@example.com",
            password="a           ",
            full_name="Test User",
        )

    # extra="forbid" must reject unexpected keys
    with pytest.raises(ValidationError):
        LoginRequest(
            email="valid@example.com",
            password="StrongPractice!2026",
            unexpectedField="hack",
        )
    with pytest.raises(ValidationError):
        OrganizationInvitationCreateRequest(
            email="invitee@example.com",
            role="ORG_MEMBER",
            extraRole="ORG_OWNER",
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

    # Reject explicit null for non-nullable settings while preserving nullable GSTIN/PAN
    with pytest.raises(ValidationError, match="cannot be null"):
        WorkspaceSettingsUpdateRequest(enable_duplicate_warnings=None)
    with pytest.raises(ValidationError, match="cannot be null"):
        WorkspaceSettingsUpdateRequest(legal_entity_name=None)
    with pytest.raises(ValidationError, match="cannot be null"):
        WorkspaceSettingsUpdateRequest(rounding_tolerance=None)
    cleared_tax_ids = WorkspaceSettingsUpdateRequest(company_gstin=None, company_pan=None)
    assert cleared_tax_ids.company_gstin is None
    assert cleared_tax_ids.company_pan is None

    # Validate GSTIN, PAN, defaultCurrency, and 2-decimal roundingTolerance precision
    with pytest.raises(ValidationError, match="GSTIN"):
        WorkspaceSettingsUpdateRequest(company_gstin="INVALIDGSTIN123")
    with pytest.raises(ValidationError, match="PAN"):
        WorkspaceSettingsUpdateRequest(company_pan="BADPAN1234")
    with pytest.raises(ValidationError, match="currency"):
        WorkspaceSettingsUpdateRequest(default_currency="123")
    with pytest.raises(ValidationError):
        WorkspaceSettingsUpdateRequest(rounding_tolerance=Decimal("1.234"))

    valid_tax_ids = WorkspaceSettingsUpdateRequest(
        company_gstin="27aabcb1234m1z5",
        company_pan="aabcb1234m",
        default_currency="inr",
        rounding_tolerance=Decimal("1.25"),
    )
    assert valid_tax_ids.company_gstin == "27AABCB1234M1Z5"
    assert valid_tax_ids.company_pan == "AABCB1234M"
    assert valid_tax_ids.default_currency == "INR"
    assert valid_tax_ids.rounding_tolerance == Decimal("1.25")


def test_is_allowed_request_origin_enforces_staging_and_production_headers() -> None:
    from starlette.requests import Request

    from app.core.cookies import is_allowed_request_origin

    def _make_request(headers: list[tuple[bytes, bytes]]) -> Request:
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": headers,
        }
        return Request(scope)

    dev_settings = _security_settings()
    staging_settings = Settings(
        _env_file=None,
        app_env="staging",
        database_url="postgresql+psycopg://postgres:test_only@localhost:5432/norus_billwise_test",
        jwt_secret_key="staging-test-only-signing-secret-with-32-chars",
        cookie_secure=True,
        cors_origins=["https://app.norus.example"],
    )

    # Disallowed Origin always rejected even if Referer matches
    bad_origin_req = _make_request(
        [
            (b"origin", b"https://evil.example"),
            (b"referer", b"https://app.norus.example/login"),
        ]
    )
    assert is_allowed_request_origin(bad_origin_req, dev_settings) is False
    assert is_allowed_request_origin(bad_origin_req, staging_settings) is False

    # Valid Referer fallback accepted when Origin omitted
    good_referer_req = _make_request(
        [(b"referer", b"https://app.norus.example/login?next=/workspaces")]
    )
    assert is_allowed_request_origin(good_referer_req, staging_settings) is True

    # Missing Origin & Referer allowed in test/dev, rejected in staging/production
    no_headers_req = _make_request([])
    assert is_allowed_request_origin(no_headers_req, dev_settings) is True
    assert is_allowed_request_origin(no_headers_req, staging_settings) is False


def test_audit_service_truncates_long_ip_addresses() -> None:
    from app.models.review import AuditEvent
    from app.services.audit_service import record_audit_event

    added: list[AuditEvent] = []

    class _MockSession:
        def add(self, obj: AuditEvent) -> None:
            added.append(obj)

    record_audit_event(
        _MockSession(),  # type: ignore[arg-type]
        organization_id=uuid.uuid4(),
        actor_user=None,
        event_type="auth.login",
        entity_type="session",
        entity_id=uuid.uuid4(),
        summary="Recorded event",
        ip_address="2001:0db8:85a3:0000:0000:8a2e:0370:7334:" + ("x" * 64),
    )
    assert len(added) == 1
    assert added[0].ip_address is not None
    assert len(added[0].ip_address) == 64


def test_unhandled_exception_returns_sanitized_500_internal_error_envelope() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(_security_settings())

    @app.get("/api/v1/_test-unhandled-error")
    def _boom() -> None:
        raise RuntimeError("sensitive internal db connection string secret")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/v1/_test-unhandled-error")
    assert resp.status_code == 500
    body = resp.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["requestId"]
    assert "sensitive internal db connection string secret" not in resp.text


def test_get_client_ip_enforces_trusted_proxies_and_rejects_spoofing() -> None:
    from starlette.requests import Request

    from app.core.deps import get_client_ip

    def _req(
        client_host: str | None,
        headers: list[tuple[bytes, bytes]] | None = None,
    ) -> Request:
        scope: dict[str, object] = {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": headers or [],
        }
        if client_host is not None:
            scope["client"] = (client_host, 443)
        return Request(scope)  # type: ignore[arg-type]

    no_proxy_settings = _security_settings()
    assert no_proxy_settings.trusted_proxies == []

    # Without trusted proxies, X-Forwarded-For is always ignored
    assert (
        get_client_ip(
            _req("198.51.100.10", [(b"x-forwarded-for", b"203.0.113.99")]),
            no_proxy_settings,
        )
        == "198.51.100.10"
    )

    trusted_settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+psycopg://postgres:test_only@localhost:5432/norus_billwise_test",
        jwt_secret_key="unit-test-only-signing-secret-with-32-plus-chars",
        cookie_secure=False,
        cors_origins=["http://localhost:3000"],
        trusted_proxies=["10.0.0.0/8", "fd00::/8"],
    )

    # Untrusted peer cannot spoof X-Forwarded-For
    assert (
        get_client_ip(
            _req("198.51.100.10", [(b"x-forwarded-for", b"203.0.113.99")]),
            trusted_settings,
        )
        == "198.51.100.10"
    )

    # Trusted proxy with spoofed leftmost IP + real appended client IP -> picks rightmost untrusted hop
    assert (
        get_client_ip(
            _req("10.0.0.5", [(b"x-forwarded-for", b"1.2.3.4, 203.0.113.50")]),
            trusted_settings,
        )
        == "203.0.113.50"
    )

    # Multi-hop trusted proxies -> walks past trusted proxy hops to real client
    assert (
        get_client_ip(
            _req(
                "10.0.0.5",
                [(b"x-forwarded-for", b"1.2.3.4, 203.0.113.50, 10.0.0.2")],
            ),
            trusted_settings,
        )
        == "203.0.113.50"
    )

    # Malformed header from trusted proxy fails safe back to direct proxy IP
    assert (
        get_client_ip(
            _req("10.0.0.5", [(b"x-forwarded-for", b"malformed-ip-header")]),
            trusted_settings,
        )
        == "10.0.0.5"
    )

    # IPv6 trusted CIDR support
    assert (
        get_client_ip(
            _req("fd00::12", [(b"x-forwarded-for", b"2001:db8::42")]),
            trusted_settings,
        )
        == "2001:db8::42"
    )

    # Missing client returns None
    assert get_client_ip(_req(None), trusted_settings) is None

