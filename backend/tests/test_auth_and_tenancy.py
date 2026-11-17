from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Generator
from contextlib import ExitStack
from datetime import timedelta
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.cookies import ACCESS_COOKIE_NAME, CSRF_COOKIE_NAME, REFRESH_COOKIE_NAME
from app.core.security import create_access_token, hash_refresh_token
from app.main import create_app
from app.models.review import AuditEvent
from app.models.tenancy import (
    OrganizationMembership,
    User,
    UserSession,
    WorkspaceSettings,
)
from tests.conftest import TEST_JWT_SECRET
from tests.test_migrations import (
    ALLOWED_POSTGRES_SCHEMES,
    APPROVED_TEST_HOSTS,
    REQUIRED_TEST_DATABASE_NAME,
    MigrationTestSafetyError,
)


def _validate_integration_postgres_url(
    raw_url: str | None, *, require_postgres: bool
) -> str | None:
    cleaned = (raw_url or "").strip()
    if not cleaned:
        if require_postgres:
            raise MigrationTestSafetyError(
                "TEST_DATABASE_URL is required when NORUS_REQUIRE_POSTGRES_TESTS=1."
            )
        return None

    parsed = urlparse(cleaned)
    if parsed.scheme.lower() not in ALLOWED_POSTGRES_SCHEMES:
        raise MigrationTestSafetyError(
            "TEST_DATABASE_URL must use postgresql:// or postgresql+psycopg://."
        )
    hostname = (parsed.hostname or "").lower()
    if hostname not in APPROVED_TEST_HOSTS:
        raise MigrationTestSafetyError(
            f"Refusing integration test DB connection on unapproved host {hostname!r}."
        )
    db_name = parsed.path.lstrip("/")
    if db_name != REQUIRED_TEST_DATABASE_NAME:
        raise MigrationTestSafetyError(
            f"Integration tests require database {REQUIRED_TEST_DATABASE_NAME!r}, got {db_name!r}."
        )
    return cleaned


@pytest.fixture(scope="module")
def pg_test_url() -> str:
    require_pg = os.environ.get("NORUS_REQUIRE_POSTGRES_TESTS", "").strip() == "1"
    raw_url = os.environ.get("TEST_DATABASE_URL", "")
    try:
        validated = _validate_integration_postgres_url(
            raw_url, require_postgres=require_pg
        )
    except MigrationTestSafetyError as exc:
        pytest.fail(str(exc), pytrace=False)

    if validated is None:
        pytest.skip(
            "TEST_DATABASE_URL is not set; skipping PostgreSQL auth & tenancy integration tests."
        )

    engine = create_engine(validated, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        engine.dispose()
        error_type = type(exc).__name__
        if require_pg:
            pytest.fail(
                f"PostgreSQL integration test failed: database unreachable ({error_type}) "
                "while NORUS_REQUIRE_POSTGRES_TESTS=1.",
                pytrace=False,
            )
        pytest.skip(f"PostgreSQL unavailable for integration tests ({error_type}).")

    # Ensure schema is migrated to head regardless of test collection order
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    alembic_cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    alembic_cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", validated)
    command.upgrade(alembic_cfg, "head")
    engine.dispose()
    return validated


@pytest.fixture
def pg_settings(pg_test_url: str) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=pg_test_url,
        jwt_secret_key=TEST_JWT_SECRET,
        cookie_secure=False,
        cors_origins=["http://localhost:3000", "https://app.norus.example"],
        log_level="WARNING",
        access_token_expire_minutes=15,
        refresh_token_expire_days=14,
    )


@pytest.fixture
def db_session(pg_test_url: str) -> Generator[Session, None, None]:
    engine = create_engine(pg_test_url, pool_pre_ping=True)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session
    engine.dispose()


@pytest.fixture
def make_client(
    pg_settings: Settings,
) -> Generator[Callable[..., TestClient], None, None]:
    stack = ExitStack()

    def _factory(
        *,
        custom_settings: Settings | None = None,
        base_url: str = "http://testserver",
    ) -> TestClient:
        get_settings.cache_clear()
        app = create_app(custom_settings or pg_settings)
        client = stack.enter_context(TestClient(app, base_url=base_url))
        return client

    yield _factory
    stack.close()
    get_settings.cache_clear()


def _csrf_headers(client: TestClient, *, origin: str | None = None) -> dict[str, str]:
    token = client.cookies.get(CSRF_COOKIE_NAME)
    headers: dict[str, str] = {}
    if token:
        headers["X-CSRF-Token"] = token
    if origin:
        headers["Origin"] = origin
    return headers


def _register_user(
    client: TestClient,
    *,
    prefix: str,
    full_name: str = "CA Ananya Deshmukh",
    org_name: str | None = None,
    password: str = "StrongPractice!2026",
) -> dict:
    uid = uuid.uuid4().hex[:10]
    email = f"{prefix}.{uid}@example.invalid"
    payload: dict[str, object] = {
        "email": email,
        "password": password,
        "fullName": full_name,
    }
    if org_name is not None:
        payload["organizationName"] = org_name
        payload["firmType"] = "Chartered Accountancy Practice"

    resp = client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_registration_duplicate_email_cookies_and_audit_trail(
    make_client: Callable[..., TestClient],
    db_session: Session,
) -> None:
    client = make_client()
    uid = uuid.uuid4().hex[:10]
    email = f"Founder.{uid}@example.invalid"

    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPractice!2026",
            "fullName": "CA Ananya Deshmukh",
            "organizationName": f"Deshmukh Practice {uid}",
            "firmType": "Chartered Accountancy Practice",
        },
    )
    assert reg_resp.status_code == 201
    body = reg_resp.json()

    # Tokens must NEVER appear in JSON bodies
    assert "accessToken" not in body
    assert "refreshToken" not in body
    assert "access_token" not in body
    assert "refresh_token" not in body
    assert body["user"]["email"] == email.lower()
    assert body["organization"]["role"] == "ORG_OWNER"
    assert body["workspace"]["role"] == "WORKSPACE_ADMIN"
    assert body["sessionExpiresAt"]

    # Verify Set-Cookie attributes on registration
    set_cookies = reg_resp.headers.get_list("set-cookie")
    joined = "\n".join(set_cookies)
    assert f"{ACCESS_COOKIE_NAME}=" in joined
    assert f"{REFRESH_COOKIE_NAME}=" in joined
    assert f"{CSRF_COOKIE_NAME}=" in joined

    access_header = next(h for h in set_cookies if h.startswith(f"{ACCESS_COOKIE_NAME}="))
    refresh_header = next(h for h in set_cookies if h.startswith(f"{REFRESH_COOKIE_NAME}="))
    csrf_header = next(h for h in set_cookies if h.startswith(f"{CSRF_COOKIE_NAME}="))

    assert "HttpOnly" in access_header
    assert "Path=/api/v1" in access_header
    assert "samesite=lax" in access_header.lower()

    assert "HttpOnly" in refresh_header
    assert "Path=/api/v1/auth" in refresh_header
    assert "samesite=lax" in refresh_header.lower()

    assert "HttpOnly" not in csrf_header
    assert "Path=/" in csrf_header
    assert "samesite=lax" in csrf_header.lower()

    # Verify DB holds Argon2id hash, SHA-256 refresh hash (not raw cookie), and human-review=true
    user_id = uuid.UUID(body["user"]["id"])
    ws_id = uuid.UUID(body["workspace"]["workspaceId"])
    db_user = db_session.get(User, user_id)
    assert db_user is not None
    assert db_user.password_hash.startswith("$argon2id$")

    raw_refresh = client.cookies.get(REFRESH_COOKIE_NAME, path="/api/v1/auth")
    assert raw_refresh
    db_session_row = db_session.scalar(
        select(UserSession).where(UserSession.user_id == user_id)
    )
    assert db_session_row is not None
    assert db_session_row.refresh_token_hash != raw_refresh
    assert db_session_row.refresh_token_hash == hash_refresh_token(raw_refresh)

    ws_settings = db_session.get(WorkspaceSettings, ws_id)
    assert ws_settings is not None
    assert ws_settings.require_human_review is True

    audit_row = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.workspace_id == ws_id,
            AuditEvent.event_type == "auth.register",
        )
    )
    assert audit_row is not None

    # Duplicate email (different casing) returns 409 EMAIL_ALREADY_EXISTS
    dup_resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": email.upper(),
            "password": "AnotherStrongPassword!2026",
            "fullName": "Duplicate User",
        },
    )
    assert dup_resp.status_code == 409
    assert dup_resp.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


def test_secure_cookie_flag_when_cookie_secure_true(
    make_client: Callable[..., TestClient], pg_test_url: str
) -> None:
    prod_settings = Settings(
        _env_file=None,
        app_env="production",
        database_url=pg_test_url,
        jwt_secret_key="production-test-only-signing-secret-with-32-chars",
        cookie_secure=True,
        cors_origins=["https://app.norus.example"],
        log_level="WARNING",
    )
    client = make_client(
        custom_settings=prod_settings,
        base_url="https://app.norus.example",
    )
    uid = uuid.uuid4().hex[:10]
    resp = client.post(
        "/api/v1/auth/register",
        headers={"Origin": "https://app.norus.example"},
        json={
            "email": f"prod.cookie.{uid}@example.invalid",
            "password": "StrongPractice!2026",
            "fullName": "Production Cookie User",
            "organizationName": f"Prod Org {uid}",
        },
    )
    assert resp.status_code == 201
    for header in resp.headers.get_list("set-cookie"):
        assert "; secure" in header.lower()


def test_login_invalid_credentials_disabled_user_and_me(
    make_client: Callable[..., TestClient],
    db_session: Session,
) -> None:
    reg_client = make_client()
    uid = uuid.uuid4().hex[:10]
    reg_data = _register_user(
        reg_client,
        prefix=f"login_{uid}",
        org_name=f"Login Firm {uid}",
    )
    email = reg_data["user"]["email"]
    user_id = uuid.UUID(reg_data["user"]["id"])

    anon_client = make_client()
    bad_pw = anon_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "WrongPassword!2026"},
    )
    assert bad_pw.status_code == 401
    assert bad_pw.json()["error"]["code"] == "INVALID_CREDENTIALS"

    unknown_email = anon_client.post(
        "/api/v1/auth/login",
        json={"email": f"nobody.{uid}@example.invalid", "password": "StrongPractice!2026"},
    )
    assert unknown_email.status_code == 401
    assert unknown_email.json()["error"]["code"] == "INVALID_CREDENTIALS"

    ok_login = anon_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPractice!2026"},
    )
    assert ok_login.status_code == 200
    login_body = ok_login.json()
    assert "accessToken" not in login_body
    assert "refreshToken" not in login_body
    assert len(login_body["workspaces"]) == 1

    me_resp = anon_client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    me_body = me_resp.json()
    assert me_body["user"]["id"] == str(user_id)
    assert len(me_body["organizations"]) == 1
    assert len(me_body["workspaces"]) == 1

    # Disabled user rejected on login (403 ACCOUNT_DISABLED) and existing access cookie (401)
    user_row = db_session.get(User, user_id)
    assert user_row is not None
    user_row.is_active = False
    db_session.commit()

    disabled_me = anon_client.get("/api/v1/auth/me")
    assert disabled_me.status_code == 401

    disabled_login = make_client().post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPractice!2026"},
    )
    assert disabled_login.status_code == 403
    assert disabled_login.json()["error"]["code"] == "ACCOUNT_DISABLED"


def test_access_token_expiry_and_tampering_rejected(
    make_client: Callable[..., TestClient],
    pg_settings: Settings,
) -> None:
    client = make_client()
    reg_data = _register_user(client, prefix="jwt_guard", org_name="JWT Guard Firm")
    user_id = uuid.UUID(reg_data["user"]["id"])
    org_id = uuid.UUID(reg_data["organization"]["id"])

    # Tampered signature
    raw_access = client.cookies.get(ACCESS_COOKIE_NAME, path="/api/v1")
    assert raw_access
    tampered = f"{raw_access[:-4]}zzzz"
    tampered_client = make_client()
    tampered_client.cookies.set(ACCESS_COOKIE_NAME, tampered, path="/api/v1")
    res_tampered = tampered_client.get("/api/v1/auth/me")
    assert res_tampered.status_code == 401
    assert res_tampered.json()["error"]["code"] == "SESSION_EXPIRED_OR_REVOKED"

    # Expired access token
    expired_jwt, _ = create_access_token(
        user_id=user_id,
        session_id=uuid.uuid4(),
        organization_id=org_id,
        settings=pg_settings,
        expires_delta=timedelta(seconds=-30),
    )
    expired_client = make_client()
    expired_client.cookies.set(ACCESS_COOKIE_NAME, expired_jwt, path="/api/v1")
    res_expired = expired_client.get("/api/v1/auth/me")
    assert res_expired.status_code == 401
    assert res_expired.json()["error"]["code"] == "SESSION_EXPIRED_OR_REVOKED"


def test_csrf_enforcement_across_unsafe_endpoints(make_client: Callable[..., TestClient]) -> None:
    client = make_client()
    reg_data = _register_user(client, prefix="csrf", org_name="CSRF Practice")
    ws_id = reg_data["workspace"]["workspaceId"]
    csrf_val = client.cookies.get(CSRF_COOKIE_NAME)
    assert csrf_val

    # Missing X-CSRF-Token header -> 403 CSRF_TOKEN_INVALID
    no_header = client.post("/api/v1/auth/refresh")
    assert no_header.status_code == 403
    assert no_header.json()["error"]["code"] == "CSRF_TOKEN_INVALID"

    # Mismatched X-CSRF-Token header -> 403 CSRF_TOKEN_INVALID
    bad_header = client.patch(
        f"/api/v1/workspaces/{ws_id}/settings",
        headers={"X-CSRF-Token": "wrong-csrf-token"},
        json={"legalEntityName": "Tampered"},
    )
    assert bad_header.status_code == 403
    assert bad_header.json()["error"]["code"] == "CSRF_TOKEN_INVALID"

    # Disallowed Origin -> 403 CSRF_TOKEN_INVALID
    bad_origin = client.post(
        "/api/v1/organizations",
        headers={
            "X-CSRF-Token": csrf_val,
            "Origin": "https://attacker.example",
        },
        json={
            "name": "Evil Org",
            "firmType": "CA Practice",
            "primaryContactEmail": "evil@example.invalid",
        },
    )
    assert bad_origin.status_code == 403
    assert bad_origin.json()["error"]["code"] == "CSRF_TOKEN_INVALID"

    # Valid Origin + matching X-CSRF-Token -> succeeds
    ok_resp = client.post(
        "/api/v1/organizations",
        headers=_csrf_headers(client, origin="http://localhost:3000"),
        json={
            "name": f"Allowed Org {uuid.uuid4().hex[:6]}",
            "firmType": "CA Practice",
            "primaryContactEmail": "owner@example.invalid",
        },
    )
    assert ok_resp.status_code == 201


def test_refresh_rotation_and_replay_detection_revokes_token_family(
    make_client: Callable[..., TestClient],
    db_session: Session,
) -> None:
    client = make_client()
    reg_data = _register_user(client, prefix="refresh", org_name="Refresh Practice")
    org_id = uuid.UUID(reg_data["organization"]["id"])

    initial_access = client.cookies.get(ACCESS_COOKIE_NAME, path="/api/v1")
    initial_refresh = client.cookies.get(REFRESH_COOKIE_NAME, path="/api/v1/auth")
    assert initial_access and initial_refresh

    # 1. Valid rotation
    rot_resp = client.post(
        "/api/v1/auth/refresh",
        headers=_csrf_headers(client),
    )
    assert rot_resp.status_code == 200
    rot_body = rot_resp.json()
    assert rot_body["refreshed"] is True
    assert "accessToken" not in rot_body
    assert "refreshToken" not in rot_body

    rotated_access = client.cookies.get(ACCESS_COOKIE_NAME, path="/api/v1")
    rotated_refresh = client.cookies.get(REFRESH_COOKIE_NAME, path="/api/v1/auth")
    assert rotated_refresh and rotated_refresh != initial_refresh
    assert rotated_access and rotated_access != initial_access

    # Previous access sid was revoked during rotation
    stale_access_client = make_client()
    stale_access_client.cookies.set(ACCESS_COOKIE_NAME, initial_access, path="/api/v1")
    assert stale_access_client.get("/api/v1/auth/me").status_code == 401

    # New rotated session works on /auth/me
    assert client.get("/api/v1/auth/me").status_code == 200

    # Verify DB links old session -> new session
    old_row = db_session.scalar(
        select(UserSession).where(
            UserSession.refresh_token_hash == hash_refresh_token(initial_refresh)
        )
    )
    new_row = db_session.scalar(
        select(UserSession).where(
            UserSession.refresh_token_hash == hash_refresh_token(rotated_refresh)
        )
    )
    assert old_row is not None and new_row is not None
    assert old_row.rotated_at is not None
    assert old_row.revoke_reason == "ROTATION"
    assert old_row.replaced_by_session_id == new_row.id
    assert old_row.token_family_id == new_row.token_family_id

    # 2. Replay the already-rotated refresh token from a second client
    attacker_client = make_client()
    attacker_client.cookies.set(REFRESH_COOKIE_NAME, initial_refresh, path="/api/v1/auth")
    attacker_client.cookies.set(CSRF_COOKIE_NAME, "replay-csrf-token", path="/")
    replay_resp = attacker_client.post(
        "/api/v1/auth/refresh",
        headers={"X-CSRF-Token": "replay-csrf-token"},
    )
    assert replay_resp.status_code == 401
    assert replay_resp.json()["error"]["code"] == "SESSION_EXPIRED_OR_REVOKED"

    # Entire token family must now be revoked (legitimate client's active session is killed too)
    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        client.post("/api/v1/auth/refresh", headers=_csrf_headers(client)).status_code
        == 401
    )

    db_session.expire_all()
    refreshed_new_row = db_session.get(UserSession, new_row.id)
    assert refreshed_new_row is not None
    assert refreshed_new_row.revoked_at is not None
    assert refreshed_new_row.revoke_reason == "REFRESH_TOKEN_REUSE_DETECTED"

    reuse_audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.organization_id == org_id,
            AuditEvent.event_type == "auth.refresh_reuse_detected",
        )
    )
    assert reuse_audit is not None
    assert reuse_audit.tone == "warning"


def test_logout_and_logout_all_revoke_sessions_immediately(
    make_client: Callable[..., TestClient],
) -> None:
    client_one = make_client()
    reg_data = _register_user(client_one, prefix="logout", org_name="Logout Practice")
    email = reg_data["user"]["email"]

    saved_access_one = client_one.cookies.get(ACCESS_COOKIE_NAME, path="/api/v1")
    assert saved_access_one

    # Logout current session
    logout_resp = client_one.post(
        "/api/v1/auth/logout",
        headers=_csrf_headers(client_one),
    )
    assert logout_resp.status_code == 204

    # Even if attacker replays the prior access cookie, sid check fails immediately
    replay_one = make_client()
    replay_one.cookies.set(ACCESS_COOKIE_NAME, saved_access_one, path="/api/v1")
    assert replay_one.get("/api/v1/auth/me").status_code == 401

    # Open two concurrent sessions across separate clients and invoke logout-all
    device_a = make_client()
    device_b = make_client()
    assert (
        device_a.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "StrongPractice!2026"},
        ).status_code
        == 200
    )
    assert (
        device_b.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "StrongPractice!2026"},
        ).status_code
        == 200
    )
    assert device_a.get("/api/v1/auth/me").status_code == 200
    assert device_b.get("/api/v1/auth/me").status_code == 200

    logout_all_resp = device_a.post(
        "/api/v1/auth/logout-all",
        headers=_csrf_headers(device_a),
    )
    assert logout_all_resp.status_code == 204

    assert device_a.get("/api/v1/auth/me").status_code == 401
    assert device_b.get("/api/v1/auth/me").status_code == 401
    assert (
        device_b.post("/api/v1/auth/refresh", headers=_csrf_headers(device_b)).status_code
        == 401
    )


def test_organization_workspace_provisioning_and_cross_tenant_isolation(
    make_client: Callable[..., TestClient],
    db_session: Session,
) -> None:
    owner_client = make_client()
    owner_reg = _register_user(
        owner_client, prefix="org_owner", org_name="Alpha CA Associates"
    )
    org_id = uuid.UUID(owner_reg["organization"]["id"])

    # Owner creates a 2nd organization and provisions a workspace inside it
    org_create = owner_client.post(
        "/api/v1/organizations",
        headers=_csrf_headers(owner_client),
        json={
            "name": f"Beta Advisory {uuid.uuid4().hex[:6]}",
            "firmType": "Enterprise Finance",
            "primaryContactEmail": "finance@beta.example",
        },
    )
    assert org_create.status_code == 201
    second_org_id = org_create.json()["id"]

    ws_create = owner_client.post(
        f"/api/v1/organizations/{second_org_id}/workspaces",
        headers=_csrf_headers(owner_client),
        json={
            "name": "Beta Client Co",
            "workspaceCode": f"WS-{uuid.uuid4().hex[:6]}",
            "legalEntityName": "Beta Client Private Limited",
            "companyGstin": "27aabcb1234m1z5",
            "companyPan": "aabcb1234m",
            "registeredAddress": "Mumbai, MH",
        },
    )
    assert ws_create.status_code == 201
    ws_body = ws_create.json()
    assert ws_body["workspace"]["currentUserRole"] == "WORKSPACE_ADMIN"
    assert ws_body["settings"]["requireHumanReview"] is True
    assert ws_body["settings"]["companyGstin"] == "27AABCB1234M1Z5"
    assert ws_body["settings"]["companyPan"] == "AABCB1234M"

    # Org list returns both organizations; workspace filter narrows by organizationId
    orgs_list = owner_client.get("/api/v1/organizations").json()["items"]
    assert len(orgs_list) == 2

    filtered_ws = owner_client.get(
        f"/api/v1/workspaces?organizationId={second_org_id}"
    ).json()["items"]
    assert len(filtered_ws) == 1
    assert filtered_ws[0]["organizationId"] == second_org_id

    # Outsider User B gets 404 (not 403) across organization & workspace routes
    outsider_client = make_client()
    outsider_reg = _register_user(
        outsider_client, prefix="outsider", org_name="Unrelated Firm"
    )
    outsider_user_id = uuid.UUID(outsider_reg["user"]["id"])
    target_ws_id = ws_body["workspace"]["id"]

    assert outsider_client.get(f"/api/v1/workspaces/{target_ws_id}").status_code == 404
    assert (
        outsider_client.get(f"/api/v1/workspaces/{target_ws_id}/settings").status_code
        == 404
    )
    assert (
        outsider_client.patch(
            f"/api/v1/workspaces/{target_ws_id}/settings",
            headers=_csrf_headers(outsider_client),
            json={"legalEntityName": "Hijacked"},
        ).status_code
        == 404
    )
    assert (
        outsider_client.get(f"/api/v1/workspaces/{target_ws_id}/memberships").status_code
        == 404
    )
    assert (
        outsider_client.get(f"/api/v1/workspaces/{target_ws_id}/audit-events").status_code
        == 404
    )
    assert (
        outsider_client.post(
            f"/api/v1/organizations/{org_id}/workspaces",
            headers=_csrf_headers(outsider_client),
            json={
                "name": "Forbidden WS",
                "workspaceCode": "WS-FORBID",
                "legalEntityName": "Forbidden Entity",
            },
        ).status_code
        == 404
    )

    # Grant outsider ORG_MEMBER on org_id -> allowed in org, still 403 on workspace creation
    db_session.add(
        OrganizationMembership(
            organization_id=org_id,
            user_id=outsider_user_id,
            role="ORG_MEMBER",
            status="ACTIVE",
        )
    )
    db_session.commit()

    org_member_attempt = outsider_client.post(
        f"/api/v1/organizations/{org_id}/workspaces",
        headers=_csrf_headers(outsider_client),
        json={
            "name": "Member Attempt WS",
            "workspaceCode": "WS-MEM-01",
            "legalEntityName": "Member Attempt Co",
        },
    )
    assert org_member_attempt.status_code == 403
    assert org_member_attempt.json()["error"]["code"] == "FORBIDDEN_ROLE"

    # Upgrade to ORG_ADMIN -> succeeds in provisioning new workspace
    org_mem_row = db_session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.user_id == outsider_user_id,
        )
    )
    assert org_mem_row is not None
    org_mem_row.role = "ORG_ADMIN"
    db_session.commit()

    org_admin_ws = outsider_client.post(
        f"/api/v1/organizations/{org_id}/workspaces",
        headers=_csrf_headers(outsider_client),
        json={
            "name": "Admin Created Client",
            "workspaceCode": f"WS-{uuid.uuid4().hex[:6]}",
            "legalEntityName": "Admin Created Client LLP",
        },
    )
    assert org_admin_ws.status_code == 201


def test_workspace_rbac_roles_and_require_human_review_immutable(
    make_client: Callable[..., TestClient],
    db_session: Session,
) -> None:
    admin_client = make_client()
    admin_reg = _register_user(
        admin_client, prefix="rbac_admin", org_name="RBAC Chartered Firm"
    )
    ws_id = admin_reg["workspace"]["workspaceId"]
    org_id = admin_reg["organization"]["id"]

    # Register Reviewer, Uploader, and Viewer accounts
    reviewer_client = make_client()
    reviewer_email = _register_user(reviewer_client, prefix="rbac_rev")["user"]["email"]

    uploader_client = make_client()
    uploader_reg = _register_user(uploader_client, prefix="rbac_upl")
    uploader_email = uploader_reg["user"]["email"]
    uploader_user_id = uploader_reg["user"]["id"]

    viewer_client = make_client()
    viewer_email = _register_user(viewer_client, prefix="rbac_view")["user"]["email"]

    for email, role in [
        (reviewer_email, "REVIEWER"),
        (uploader_email, "UPLOADER"),
        (viewer_email, "VIEWER"),
    ]:
        add_resp = admin_client.post(
            f"/api/v1/workspaces/{ws_id}/memberships",
            headers=_csrf_headers(admin_client),
            json={"email": email, "role": role},
        )
        assert add_resp.status_code == 201, add_resp.text

    # Human-review gate cannot be disabled during workspace creation or settings PATCH
    create_disabled = admin_client.post(
        f"/api/v1/organizations/{org_id}/workspaces",
        headers=_csrf_headers(admin_client),
        json={
            "name": "Unsafe Client",
            "workspaceCode": f"WS-UNSAFE-{uuid.uuid4().hex[:4]}",
            "legalEntityName": "Unsafe Entity",
            "requireHumanReview": False,
        },
    )
    assert create_disabled.status_code == 422
    assert create_disabled.json()["error"]["code"] == "HUMAN_REVIEW_CANNOT_BE_DISABLED"

    patch_disabled = admin_client.patch(
        f"/api/v1/workspaces/{ws_id}/settings",
        headers=_csrf_headers(admin_client),
        json={"requireHumanReview": False},
    )
    assert patch_disabled.status_code == 422
    assert patch_disabled.json()["error"]["code"] == "HUMAN_REVIEW_CANNOT_BE_DISABLED"

    # Admin updates editable settings cleanly; requireHumanReview stays locked True
    patch_ok = admin_client.patch(
        f"/api/v1/workspaces/{ws_id}/settings",
        headers=_csrf_headers(admin_client),
        json={
            "legalEntityName": "Updated Legal Practice LLP",
            "roundingTolerance": "1.50",
            "enableDuplicateWarnings": False,
        },
    )
    assert patch_ok.status_code == 200
    assert patch_ok.json()["requireHumanReview"] is True
    assert patch_ok.json()["roundingTolerance"] == "1.50"
    assert patch_ok.json()["enableDuplicateWarnings"] is False

    db_settings = db_session.get(WorkspaceSettings, uuid.UUID(ws_id))
    assert db_settings is not None
    assert db_settings.require_human_review is True

    # REVIEWER & VIEWER can view workspace, settings, memberships, and audit-events; rejected on mutations
    for non_admin_client, expected_role in [
        (reviewer_client, "REVIEWER"),
        (viewer_client, "VIEWER"),
    ]:
        detail = non_admin_client.get(f"/api/v1/workspaces/{ws_id}")
        assert detail.status_code == 200
        assert detail.json()["currentUserRole"] == expected_role
        assert non_admin_client.get(f"/api/v1/workspaces/{ws_id}/settings").status_code == 200
        assert non_admin_client.get(f"/api/v1/workspaces/{ws_id}/memberships").status_code == 200
        assert non_admin_client.get(f"/api/v1/workspaces/{ws_id}/audit-events").status_code == 200

        assert (
            non_admin_client.patch(
                f"/api/v1/workspaces/{ws_id}/settings",
                headers=_csrf_headers(non_admin_client),
                json={"legalEntityName": "Unauthorized Update"},
            ).status_code
            == 403
        )
        assert (
            non_admin_client.post(
                f"/api/v1/workspaces/{ws_id}/memberships",
                headers=_csrf_headers(non_admin_client),
                json={"email": "someone@example.invalid", "role": "VIEWER"},
            ).status_code
            == 403
        )

    # UPLOADER can view workspace/settings, forbidden from memberships, audit-events scoped to own actor events
    assert uploader_client.get(f"/api/v1/workspaces/{ws_id}").status_code == 200
    assert uploader_client.get(f"/api/v1/workspaces/{ws_id}/settings").status_code == 200
    assert uploader_client.get(f"/api/v1/workspaces/{ws_id}/memberships").status_code == 403

    admin_audits = admin_client.get(f"/api/v1/workspaces/{ws_id}/audit-events").json()
    assert admin_audits["total"] >= 4
    uploader_audits = uploader_client.get(
        f"/api/v1/workspaces/{ws_id}/audit-events"
    ).json()
    assert all(
        item["actorUserId"] == uploader_user_id for item in uploader_audits["items"]
    )


def test_last_admin_protection_and_session_revocation_on_membership_mutation(
    make_client: Callable[..., TestClient],
    db_session: Session,
) -> None:
    admin_client = make_client()
    admin_reg = _register_user(
        admin_client, prefix="last_admin", org_name="Last Admin Practice"
    )
    ws_id = admin_reg["workspace"]["workspaceId"]

    members = admin_client.get(f"/api/v1/workspaces/{ws_id}/memberships").json()["items"]
    assert len(members) == 1
    sole_admin_membership_id = members[0]["id"]

    # Sole active WORKSPACE_ADMIN cannot be downgraded, suspended, or removed
    downgrade_sole = admin_client.patch(
        f"/api/v1/workspaces/{ws_id}/memberships/{sole_admin_membership_id}",
        headers=_csrf_headers(admin_client),
        json={"role": "REVIEWER"},
    )
    assert downgrade_sole.status_code == 409
    assert downgrade_sole.json()["error"]["code"] == "CANNOT_DOWNGRADE_LAST_ADMIN"

    suspend_sole = admin_client.patch(
        f"/api/v1/workspaces/{ws_id}/memberships/{sole_admin_membership_id}",
        headers=_csrf_headers(admin_client),
        json={"status": "SUSPENDED"},
    )
    assert suspend_sole.status_code == 409
    assert suspend_sole.json()["error"]["code"] == "CANNOT_DOWNGRADE_LAST_ADMIN"

    delete_sole = admin_client.delete(
        f"/api/v1/workspaces/{ws_id}/memberships/{sole_admin_membership_id}",
        headers=_csrf_headers(admin_client),
    )
    assert delete_sole.status_code == 409
    assert delete_sole.json()["error"]["code"] == "CANNOT_DOWNGRADE_LAST_ADMIN"

    # Add User 2 as Reviewer, verify duplicate membership returns 409
    user2_client = make_client()
    user2_reg = _register_user(user2_client, prefix="member_two")
    user2_email = user2_reg["user"]["email"]

    added_u2 = admin_client.post(
        f"/api/v1/workspaces/{ws_id}/memberships",
        headers=_csrf_headers(admin_client),
        json={"email": user2_email, "role": "REVIEWER"},
    )
    assert added_u2.status_code == 201
    u2_membership_id = added_u2.json()["id"]

    dup_member = admin_client.post(
        f"/api/v1/workspaces/{ws_id}/memberships",
        headers=_csrf_headers(admin_client),
        json={"email": user2_email, "role": "VIEWER"},
    )
    assert dup_member.status_code == 409
    assert dup_member.json()["error"]["code"] == "MEMBERSHIP_ALREADY_EXISTS"

    # Promote User 2 to WORKSPACE_ADMIN -> downgrading User 2 revokes User 2's active session
    assert user2_client.get("/api/v1/auth/me").status_code == 200
    promote_u2 = admin_client.patch(
        f"/api/v1/workspaces/{ws_id}/memberships/{u2_membership_id}",
        headers=_csrf_headers(admin_client),
        json={"role": "WORKSPACE_ADMIN"},
    )
    assert promote_u2.status_code == 200
    assert user2_client.get("/api/v1/auth/me").status_code == 401

    # Now with 2 active admins, downgrading User 1 (sole_admin) succeeds and revokes User 1 session
    downgrade_u1 = admin_client.patch(
        f"/api/v1/workspaces/{ws_id}/memberships/{sole_admin_membership_id}",
        headers=_csrf_headers(admin_client),
        json={"role": "REVIEWER"},
    )
    assert downgrade_u1.status_code == 200
    assert admin_client.get("/api/v1/auth/me").status_code == 401

    # Log User 2 back in as sole remaining WORKSPACE_ADMIN, suspend then delete User 1
    assert (
        user2_client.post(
            "/api/v1/auth/login",
            json={"email": user2_email, "password": "StrongPractice!2026"},
        ).status_code
        == 200
    )
    assert (
        admin_client.post(
            "/api/v1/auth/login",
            json={"email": admin_reg["user"]["email"], "password": "StrongPractice!2026"},
        ).status_code
        == 200
    )
    assert admin_client.get(f"/api/v1/workspaces/{ws_id}").status_code == 200

    suspend_u1 = user2_client.patch(
        f"/api/v1/workspaces/{ws_id}/memberships/{sole_admin_membership_id}",
        headers=_csrf_headers(user2_client),
        json={"status": "SUSPENDED"},
    )
    assert suspend_u1.status_code == 200
    assert admin_client.get("/api/v1/auth/me").status_code == 401

    # Even if suspended User 1 re-authenticates, workspace returns 404 WORKSPACE_NOT_FOUND
    assert (
        admin_client.post(
            "/api/v1/auth/login",
            json={"email": admin_reg["user"]["email"], "password": "StrongPractice!2026"},
        ).status_code
        == 200
    )
    assert admin_client.get(f"/api/v1/workspaces/{ws_id}").status_code == 404

    delete_u1 = user2_client.delete(
        f"/api/v1/workspaces/{ws_id}/memberships/{sole_admin_membership_id}",
        headers=_csrf_headers(user2_client),
    )
    assert delete_u1.status_code == 204
    assert admin_client.get("/api/v1/auth/me").status_code == 401

    # Verify all membership lifecycle audit events exist in PostgreSQL
    events = list(
        db_session.scalars(
            select(AuditEvent.event_type).where(
                AuditEvent.workspace_id == uuid.UUID(ws_id)
            )
        )
    )
    assert "membership.created" in events
    assert "membership.updated" in events
    assert "membership.suspended" in events
    assert "membership.removed" in events
