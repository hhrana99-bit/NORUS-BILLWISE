from __future__ import annotations

import os
import threading
import uuid
from collections.abc import Callable, Generator
from concurrent.futures import ThreadPoolExecutor
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
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    User,
    UserSession,
    Workspace,
    WorkspaceSettings,
    utc_now,
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
    pg_test_url: str,
) -> Generator[Callable[..., TestClient], None, None]:
    # Isolate PostgreSQL rate-limit buckets between tests while allowing multiple
    # TestClient instances within the same test to share rate-limit state.
    clean_engine = create_engine(pg_test_url, pool_pre_ping=True)
    with clean_engine.begin() as conn:
        conn.execute(text("DELETE FROM auth_rate_limit_buckets"))
    clean_engine.dispose()

    stack = ExitStack()

    def _factory(
        *,
        custom_settings: Settings | None = None,
        base_url: str = "http://testserver",
        raise_server_exceptions: bool = True,
    ) -> TestClient:
        get_settings.cache_clear()
        app = create_app(custom_settings or pg_settings)
        client = stack.enter_context(
            TestClient(
                app,
                base_url=base_url,
                raise_server_exceptions=raise_server_exceptions,
            )
        )
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


def _onboard_user_to_org(
    org_admin_client: TestClient,
    *,
    org_id: str,
    member_client: TestClient,
    email: str,
    role: str = "ORG_MEMBER",
) -> str:
    invite_resp = org_admin_client.post(
        f"/api/v1/organizations/{org_id}/invitations",
        headers=_csrf_headers(org_admin_client),
        json={"email": email, "role": role},
    )
    assert invite_resp.status_code == 201, invite_resp.text
    raw_token = invite_resp.json()["inviteToken"]
    assert raw_token

    accept_resp = member_client.post(
        "/api/v1/organizations/invitations/accept",
        headers=_csrf_headers(member_client),
        json={"token": raw_token},
    )
    assert accept_resp.status_code == 200, accept_resp.text
    return raw_token


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

    # Register Reviewer, Uploader, and Viewer accounts and onboard them into org_id
    reviewer_client = make_client()
    reviewer_email = _register_user(reviewer_client, prefix="rbac_rev")["user"]["email"]

    uploader_client = make_client()
    uploader_reg = _register_user(uploader_client, prefix="rbac_upl")
    uploader_email = uploader_reg["user"]["email"]
    uploader_user_id = uploader_reg["user"]["id"]

    viewer_client = make_client()
    viewer_email = _register_user(viewer_client, prefix="rbac_view")["user"]["email"]

    # Adding a user to a workspace before org onboarding must fail uniformly with 404
    pre_onboard_add = admin_client.post(
        f"/api/v1/workspaces/{ws_id}/memberships",
        headers=_csrf_headers(admin_client),
        json={"email": reviewer_email, "role": "REVIEWER"},
    )
    assert pre_onboard_add.status_code == 404
    assert pre_onboard_add.json()["error"]["code"] == "ORGANIZATION_MEMBER_NOT_FOUND"

    for member_client, member_email in [
        (reviewer_client, reviewer_email),
        (uploader_client, uploader_email),
        (viewer_client, viewer_email),
    ]:
        _onboard_user_to_org(
            admin_client,
            org_id=org_id,
            member_client=member_client,
            email=member_email,
        )

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

    # Add User 2 via invitation onboarding, grant Reviewer, verify duplicate returns 409
    user2_client = make_client()
    user2_reg = _register_user(user2_client, prefix="member_two")
    user2_email = user2_reg["user"]["email"]
    _onboard_user_to_org(
        admin_client,
        org_id=admin_reg["organization"]["id"],
        member_client=user2_client,
        email=user2_email,
    )

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


# ---------------------------------------------------------------------------
# Batch 2.1 security & reliability regression tests
# ---------------------------------------------------------------------------


def test_integration_postgres_url_validation_guard() -> None:
    assert (
        _validate_integration_postgres_url(
            "postgresql+psycopg://postgres:test@localhost:5432/norus_billwise_test",
            require_postgres=True,
        )
        == "postgresql+psycopg://postgres:test@localhost:5432/norus_billwise_test"
    )
    assert _validate_integration_postgres_url("", require_postgres=False) is None
    with pytest.raises(MigrationTestSafetyError):
        _validate_integration_postgres_url("", require_postgres=True)
    with pytest.raises(MigrationTestSafetyError):
        _validate_integration_postgres_url(
            "sqlite:///./local.db", require_postgres=True
        )
    with pytest.raises(MigrationTestSafetyError):
        _validate_integration_postgres_url(
            "postgresql+psycopg://u:p@db.prod.internal:5432/norus_billwise_test",
            require_postgres=True,
        )
    with pytest.raises(MigrationTestSafetyError):
        _validate_integration_postgres_url(
            "postgresql+psycopg://u:p@localhost:5432/norus_billwise_prod",
            require_postgres=True,
        )


def test_anti_enumeration_invitation_lifecycle_and_org_suspension(
    make_client: Callable[..., TestClient],
    db_session: Session,
) -> None:
    owner_client = make_client()
    owner_reg = _register_user(
        owner_client, prefix="org_sec_owner", org_name="Secure Onboarding Practice"
    )
    org_id = owner_reg["organization"]["id"]
    ws_id = owner_reg["workspace"]["workspaceId"]

    rival_client = make_client()
    rival_reg = _register_user(
        rival_client, prefix="rival_user", org_name="Rival Practice Ltd"
    )
    rival_email = rival_reg["user"]["email"]

    # Non-org member vs non-existent user MUST return identical error payload (zero enumeration)
    rival_add = owner_client.post(
        f"/api/v1/workspaces/{ws_id}/memberships",
        headers=_csrf_headers(owner_client),
        json={"email": rival_email, "role": "REVIEWER"},
    )
    ghost_add = owner_client.post(
        f"/api/v1/workspaces/{ws_id}/memberships",
        headers=_csrf_headers(owner_client),
        json={"email": f"nobody-{uuid.uuid4().hex[:8]}@example.invalid", "role": "REVIEWER"},
    )
    assert rival_add.status_code == 404
    assert ghost_add.status_code == 404
    assert rival_add.json()["error"]["code"] == "ORGANIZATION_MEMBER_NOT_FOUND"
    assert ghost_add.json()["error"]["code"] == "ORGANIZATION_MEMBER_NOT_FOUND"
    assert rival_add.json()["error"]["message"] == ghost_add.json()["error"]["message"]

    # Issue invitation: inviteToken is only returned on creation, omitted from list
    inv_create = owner_client.post(
        f"/api/v1/organizations/{org_id}/invitations",
        headers=_csrf_headers(owner_client),
        json={"email": rival_email, "role": "ORG_MEMBER"},
    )
    assert inv_create.status_code == 201
    inv_id = inv_create.json()["id"]
    inv_token = inv_create.json()["inviteToken"]
    assert inv_token

    listed_invs = owner_client.get(
        f"/api/v1/organizations/{org_id}/invitations"
    ).json()["items"]
    assert any(item["id"] == inv_id and item.get("inviteToken") is None for item in listed_invs)

    # Wrong user cannot accept another user's invitation token (403 INVITATION_EMAIL_MISMATCH)
    other_client = make_client()
    _register_user(other_client, prefix="wrong_acceptor")
    wrong_accept = other_client.post(
        "/api/v1/organizations/invitations/accept",
        headers=_csrf_headers(other_client),
        json={"token": inv_token},
    )
    assert wrong_accept.status_code == 403
    assert wrong_accept.json()["error"]["code"] == "INVITATION_EMAIL_MISMATCH"

    # Correct user accepts invitation -> can now be added to workspace
    ok_accept = rival_client.post(
        "/api/v1/organizations/invitations/accept",
        headers=_csrf_headers(rival_client),
        json={"token": inv_token},
    )
    assert ok_accept.status_code == 200
    assert ok_accept.json()["role"] == "ORG_MEMBER"

    # Re-using accepted token fails with 409 INVITATION_EXPIRED_OR_USED
    reuse_accept = rival_client.post(
        "/api/v1/organizations/invitations/accept",
        headers=_csrf_headers(rival_client),
        json={"token": inv_token},
    )
    assert reuse_accept.status_code == 409
    assert reuse_accept.json()["error"]["code"] == "INVITATION_EXPIRED_OR_USED"

    # Revoked or expired invitations fail with 409
    rev_inv = owner_client.post(
        f"/api/v1/organizations/{org_id}/invitations",
        headers=_csrf_headers(owner_client),
        json={"email": "pending.revoke@example.invalid", "role": "ORG_MEMBER"},
    ).json()
    assert (
        owner_client.delete(
            f"/api/v1/organizations/{org_id}/invitations/{rev_inv['id']}",
            headers=_csrf_headers(owner_client),
        ).status_code
        == 204
    )
    assert (
        rival_client.post(
            "/api/v1/organizations/invitations/accept",
            headers=_csrf_headers(rival_client),
            json={"token": rev_inv["inviteToken"]},
        ).status_code
        == 409
    )

    exp_inv = owner_client.post(
        f"/api/v1/organizations/{org_id}/invitations",
        headers=_csrf_headers(owner_client),
        json={"email": rival_email, "role": "ORG_MEMBER"},
    ).json()
    exp_row = db_session.get(OrganizationInvitation, uuid.UUID(exp_inv["id"]))
    assert exp_row is not None
    exp_row.expires_at = utc_now() - timedelta(minutes=5)
    db_session.commit()
    assert (
        rival_client.post(
            "/api/v1/organizations/invitations/accept",
            headers=_csrf_headers(rival_client),
            json={"token": exp_inv["inviteToken"]},
        ).status_code
        == 409
    )

    # Now add onboarded rival_email to workspace
    ws_add = owner_client.post(
        f"/api/v1/workspaces/{ws_id}/memberships",
        headers=_csrf_headers(owner_client),
        json={"email": rival_email, "role": "REVIEWER"},
    )
    assert ws_add.status_code == 201
    assert rival_client.get(f"/api/v1/workspaces/{ws_id}").status_code == 200

    # List org memberships & protect sole ORG_OWNER
    org_members = owner_client.get(
        f"/api/v1/organizations/{org_id}/memberships"
    ).json()["items"]
    owner_mem = next(m for m in org_members if m["role"] == "ORG_OWNER")
    rival_mem = next(m for m in org_members if m["email"] == rival_email)

    sole_owner_downgrade = owner_client.patch(
        f"/api/v1/organizations/{org_id}/memberships/{owner_mem['id']}",
        headers=_csrf_headers(owner_client),
        json={"role": "ORG_ADMIN"},
    )
    assert sole_owner_downgrade.status_code == 409
    assert sole_owner_downgrade.json()["error"]["code"] == "CANNOT_DOWNGRADE_LAST_ORG_OWNER"

    # Suspending rival's OrganizationMembership revokes session AND blocks workspace access even after re-login
    suspend_org_mem = owner_client.patch(
        f"/api/v1/organizations/{org_id}/memberships/{rival_mem['id']}",
        headers=_csrf_headers(owner_client),
        json={"status": "SUSPENDED"},
    )
    assert suspend_org_mem.status_code == 200
    assert rival_client.get("/api/v1/auth/me").status_code == 401

    assert (
        rival_client.post(
            "/api/v1/auth/login",
            json={"email": rival_email, "password": "StrongPractice!2026"},
        ).status_code
        == 200
    )
    assert rival_client.get(f"/api/v1/workspaces/{ws_id}").status_code == 404
    ws_ids_for_rival = [
        w["id"] for w in rival_client.get("/api/v1/workspaces").json()["items"]
    ]
    assert ws_id not in ws_ids_for_rival
    me_ws_ids = [
        w["workspaceId"] for w in rival_client.get("/api/v1/auth/me").json()["workspaces"]
    ]
    assert ws_id not in me_ws_ids

    # Suspended org member also blocked from workspace membership addition uniformly (404)
    suspended_readd = owner_client.post(
        f"/api/v1/workspaces/{ws_id}/memberships",
        headers=_csrf_headers(owner_client),
        json={"email": rival_email, "role": "VIEWER"},
    )
    assert suspended_readd.status_code == 404
    assert suspended_readd.json()["error"]["code"] == "ORGANIZATION_MEMBER_NOT_FOUND"

    # Removing OrganizationMembership deletes cascading workspace memberships
    assert (
        owner_client.delete(
            f"/api/v1/organizations/{org_id}/memberships/{rival_mem['id']}",
            headers=_csrf_headers(owner_client),
        ).status_code
        == 204
    )
    assert rival_client.get("/api/v1/auth/me").status_code == 401


def test_inactive_org_and_workspace_return_404_and_hidden_from_me(
    make_client: Callable[..., TestClient],
    db_session: Session,
) -> None:
    client = make_client()
    reg = _register_user(client, prefix="deact", org_name="Deactivation Firm")
    org_id = reg["organization"]["id"]
    ws_id = reg["workspace"]["workspaceId"]

    ws_row = db_session.get(Workspace, uuid.UUID(ws_id))
    assert ws_row is not None
    ws_row.is_active = False
    db_session.commit()

    assert client.get(f"/api/v1/workspaces/{ws_id}").status_code == 404
    assert client.get("/api/v1/auth/me").json()["workspaces"] == []

    org_row = db_session.get(Organization, uuid.UUID(org_id))
    assert org_row is not None
    org_row.is_active = False
    db_session.commit()

    assert client.get("/api/v1/auth/me").json()["organizations"] == []
    assert client.get("/api/v1/organizations").json()["items"] == []


def test_login_and_register_origin_enforcement_including_staging_production(
    make_client: Callable[..., TestClient],
    pg_test_url: str,
) -> None:
    dev_client = make_client()
    reg = _register_user(dev_client, prefix="origin_chk", org_name="Origin Firm")
    email = reg["user"]["email"]

    # Disallowed Origin on /register & /login rejected with 403 CSRF_TOKEN_INVALID
    bad_reg = dev_client.post(
        "/api/v1/auth/register",
        headers={"Origin": "https://attacker.example"},
        json={
            "email": "attacker.reg@example.invalid",
            "password": "StrongPractice!2026",
            "fullName": "Attacker",
        },
    )
    assert bad_reg.status_code == 403
    assert bad_reg.json()["error"]["code"] == "CSRF_TOKEN_INVALID"

    bad_login = dev_client.post(
        "/api/v1/auth/login",
        headers={"Origin": "https://attacker.example"},
        json={"email": email, "password": "StrongPractice!2026"},
    )
    assert bad_login.status_code == 403
    assert bad_login.json()["error"]["code"] == "CSRF_TOKEN_INVALID"

    # Allowed Referer without Origin succeeds without needing pre-existing CSRF cookie
    referer_login = make_client().post(
        "/api/v1/auth/login",
        headers={"Referer": "http://localhost:3000/login?next=/"},
        json={"email": email, "password": "StrongPractice!2026"},
    )
    assert referer_login.status_code == 200

    # Staging/production requires explicit Origin or Referer on login & register
    staging_settings = Settings(
        _env_file=None,
        app_env="staging",
        database_url=pg_test_url,
        jwt_secret_key="staging-test-only-signing-secret-with-32-chars",
        cookie_secure=True,
        cors_origins=["https://app.norus.example"],
        log_level="WARNING",
    )
    staging_client = make_client(
        custom_settings=staging_settings,
        base_url="https://app.norus.example",
    )
    missing_origin_login = staging_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPractice!2026"},
    )
    assert missing_origin_login.status_code == 403
    assert missing_origin_login.json()["error"]["code"] == "CSRF_TOKEN_INVALID"

    missing_origin_register = staging_client.post(
        "/api/v1/auth/register",
        json={
            "email": "missing.origin@example.invalid",
            "password": "StrongPractice!2026",
            "fullName": "No Origin",
        },
    )
    assert missing_origin_register.status_code == 403
    assert missing_origin_register.json()["error"]["code"] == "CSRF_TOKEN_INVALID"


def test_postgresql_rate_limiting_across_login_register_and_refresh(
    make_client: Callable[..., TestClient],
    pg_test_url: str,
) -> None:
    rl_settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=pg_test_url,
        jwt_secret_key=TEST_JWT_SECRET,
        cookie_secure=False,
        cors_origins=["http://localhost:3000"],
        log_level="WARNING",
        rate_limit_enabled=True,
        rate_limit_window_seconds=60,
        register_rate_limit_max_attempts=2,
        login_rate_limit_max_attempts=3,
        refresh_rate_limit_max_attempts=2,
    )

    c1 = make_client(custom_settings=rl_settings)
    c2 = make_client(custom_settings=rl_settings)

    # /auth/register shares PostgreSQL rate-limit bucket across separate client instances
    reg1 = c1.post(
        "/api/v1/auth/register",
        json={
            "email": f"rl1.{uuid.uuid4().hex[:6]}@example.invalid",
            "password": "StrongPractice!2026",
            "fullName": "Rate Limit One",
        },
    )
    assert reg1.status_code == 201
    reg2 = c2.post(
        "/api/v1/auth/register",
        json={
            "email": f"rl2.{uuid.uuid4().hex[:6]}@example.invalid",
            "password": "StrongPractice!2026",
            "fullName": "Rate Limit Two",
        },
    )
    assert reg2.status_code == 201
    reg3 = c1.post(
        "/api/v1/auth/register",
        json={
            "email": f"rl3.{uuid.uuid4().hex[:6]}@example.invalid",
            "password": "StrongPractice!2026",
            "fullName": "Rate Limit Three",
        },
    )
    assert reg3.status_code == 429
    assert reg3.json()["error"]["code"] == "RATE_LIMITED"
    assert int(reg3.headers["Retry-After"]) >= 1

    # /auth/refresh rate-limited after 2 calls
    assert (
        c1.post("/api/v1/auth/refresh", headers=_csrf_headers(c1)).status_code == 200
    )
    assert (
        c1.post("/api/v1/auth/refresh", headers=_csrf_headers(c1)).status_code == 200
    )
    refresh_blocked = c1.post("/api/v1/auth/refresh", headers=_csrf_headers(c1))
    assert refresh_blocked.status_code == 429
    assert refresh_blocked.json()["error"]["code"] == "RATE_LIMITED"
    assert int(refresh_blocked.headers["Retry-After"]) >= 1

    # /auth/login counts failed 401 attempts even across separate clients
    for _ in range(3):
        bad = c2.post(
            "/api/v1/auth/login",
            json={"email": "nonexistent.rl@example.invalid", "password": "WrongPassword!2026"},
        )
        assert bad.status_code == 401

    login_blocked = c1.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent.rl@example.invalid", "password": "WrongPassword!2026"},
    )
    assert login_blocked.status_code == 429
    assert login_blocked.json()["error"]["code"] == "RATE_LIMITED"
    assert int(login_blocked.headers["Retry-After"]) >= 1


def test_concurrent_dual_admin_downgrade_and_refresh_race_on_postgresql(
    make_client: Callable[..., TestClient],
) -> None:
    admin1_client = make_client()
    admin1_reg = _register_user(
        admin1_client, prefix="conc_adm1", org_name="Concurrency Practice"
    )
    org_id = admin1_reg["organization"]["id"]
    ws_id = admin1_reg["workspace"]["workspaceId"]

    admin2_client = make_client()
    admin2_reg = _register_user(admin2_client, prefix="conc_adm2")
    admin2_email = admin2_reg["user"]["email"]
    _onboard_user_to_org(
        admin1_client,
        org_id=org_id,
        member_client=admin2_client,
        email=admin2_email,
    )

    admin2_add = admin1_client.post(
        f"/api/v1/workspaces/{ws_id}/memberships",
        headers=_csrf_headers(admin1_client),
        json={"email": admin2_email, "role": "WORKSPACE_ADMIN"},
    )
    assert admin2_add.status_code == 201
    members = admin1_client.get(f"/api/v1/workspaces/{ws_id}/memberships").json()["items"]
    admin1_mem_id = next(m["id"] for m in members if m["email"] == admin1_reg["user"]["email"])
    admin2_mem_id = next(m["id"] for m in members if m["email"] == admin2_email)

    # Admin 1 and Admin 2 simultaneously try to downgrade EACH OTHER -> deterministic Workspace lock
    # prevents any deadlock; exactly 1 succeeds (200) and 1 gets 409 CANNOT_DOWNGRADE_LAST_ADMIN.
    barrier = threading.Barrier(2)

    def _downgrade(client: TestClient, target_membership_id: str) -> int:
        barrier.wait(timeout=5)
        resp = client.patch(
            f"/api/v1/workspaces/{ws_id}/memberships/{target_membership_id}",
            headers=_csrf_headers(client),
            json={"role": "REVIEWER"},
        )
        return resp.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_downgrade, admin1_client, admin2_mem_id)
        f2 = pool.submit(_downgrade, admin2_client, admin1_mem_id)
        statuses = sorted([f1.result(timeout=15), f2.result(timeout=15)])

    assert statuses == [200, 409]

    # Concurrent refresh rotation using the same refresh token from two clients -> zero 500s
    race_user = make_client()
    _register_user(race_user, prefix="conc_ref")
    shared_refresh = race_user.cookies.get(REFRESH_COOKIE_NAME, path="/api/v1/auth")
    assert shared_refresh

    racer_a = make_client()
    racer_a.cookies.set(REFRESH_COOKIE_NAME, shared_refresh, path="/api/v1/auth")
    racer_a.cookies.set(CSRF_COOKIE_NAME, "csrf-race-a", path="/")

    racer_b = make_client()
    racer_b.cookies.set(REFRESH_COOKIE_NAME, shared_refresh, path="/api/v1/auth")
    racer_b.cookies.set(CSRF_COOKIE_NAME, "csrf-race-b", path="/")

    ref_barrier = threading.Barrier(2)

    def _refresh(client: TestClient, csrf_token: str) -> int:
        ref_barrier.wait(timeout=5)
        return client.post(
            "/api/v1/auth/refresh",
            headers={"X-CSRF-Token": csrf_token},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        rf1 = pool.submit(_refresh, racer_a, "csrf-race-a")
        rf2 = pool.submit(_refresh, racer_b, "csrf-race-b")
        ref_statuses = sorted([rf1.result(timeout=15), rf2.result(timeout=15)])

    assert ref_statuses == [200, 401]


def test_settings_null_rejection_duplicate_code_rollback_cookies_and_org_login_audit(
    make_client: Callable[..., TestClient],
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client()
    reg = _register_user(client, prefix="misc_checks", org_name="Strict Practice")
    org_id = reg["organization"]["id"]
    ws_id = reg["workspace"]["workspaceId"]

    # Non-nullable settings explicit null rejected (422), nullable tax IDs cleared (200)
    for null_payload in [
        {"enableDuplicateWarnings": None},
        {"roundingTolerance": None},
        {"legalEntityName": None},
    ]:
        null_resp = client.patch(
            f"/api/v1/workspaces/{ws_id}/settings",
            headers=_csrf_headers(client),
            json=null_payload,
        )
        assert null_resp.status_code == 422
        assert null_resp.json()["error"]["code"] == "VALIDATION_ERROR"

    clear_tax_resp = client.patch(
        f"/api/v1/workspaces/{ws_id}/settings",
        headers=_csrf_headers(client),
        json={"companyGstin": None, "companyPan": None},
    )
    assert clear_tax_resp.status_code == 200
    assert clear_tax_resp.json()["companyGstin"] is None
    assert clear_tax_resp.json()["companyPan"] is None

    # extra="forbid" returns 422 VALIDATION_ERROR
    extra_resp = client.patch(
        f"/api/v1/workspaces/{ws_id}/settings",
        headers=_csrf_headers(client),
        json={"unexpectedUnknownFlag": True},
    )
    assert extra_resp.status_code == 422
    assert extra_resp.json()["error"]["code"] == "VALIDATION_ERROR"

    # Duplicate workspace code in same organization returns 409 WORKSPACE_CODE_EXISTS
    dup_code = client.post(
        f"/api/v1/organizations/{org_id}/workspaces",
        headers=_csrf_headers(client),
        json={
            "name": "Duplicate Default",
            "workspaceCode": "WS-DEFAULT-001",
            "legalEntityName": "Duplicate LLP",
        },
    )
    assert dup_code.status_code == 409
    assert dup_code.json()["error"]["code"] == "WORKSPACE_CODE_EXISTS"

    # Verify auth.login is emitted at organization scope (workspace_id=None) ONLY
    other_org_client = make_client()
    other_org_client.cookies.clear()
    login_resp = other_org_client.post(
        "/api/v1/auth/login",
        json={"email": reg["user"]["email"], "password": "StrongPractice!2026"},
    )
    assert login_resp.status_code == 200

    login_events = list(
        db_session.scalars(
            select(AuditEvent).where(
                AuditEvent.organization_id == uuid.UUID(org_id),
                AuditEvent.event_type == "auth.login",
            )
        )
    )
    assert login_events
    assert all(ev.workspace_id is None for ev in login_events)

    # Verify refresh cookie Path=/api/v1/auth prevents transmission to non-auth /api/v1 routes
    @other_org_client.app.get("/api/v1/_test_cookie_scope")
    def _inspect_non_auth_cookies(request: object) -> dict[str, list[str]]:
        from fastapi import Request

        assert isinstance(request, Request)
        return {"cookieNames": sorted(request.cookies.keys())}

    @other_org_client.app.get("/api/v1/auth/_test_cookie_scope")
    def _inspect_auth_cookies(request: object) -> dict[str, list[str]]:
        from fastapi import Request

        assert isinstance(request, Request)
        return {"cookieNames": sorted(request.cookies.keys())}

    cookie_probe = other_org_client.get("/api/v1/_test_cookie_scope")
    assert cookie_probe.status_code == 200
    assert REFRESH_COOKIE_NAME not in cookie_probe.json()["cookieNames"]
    assert ACCESS_COOKIE_NAME in cookie_probe.json()["cookieNames"]
    assert CSRF_COOKIE_NAME in cookie_probe.json()["cookieNames"]

    auth_cookie_probe = other_org_client.get("/api/v1/auth/_test_cookie_scope")
    assert auth_cookie_probe.status_code == 200
    assert REFRESH_COOKIE_NAME in auth_cookie_probe.json()["cookieNames"]
    assert ACCESS_COOKIE_NAME in auth_cookie_probe.json()["cookieNames"]
    assert CSRF_COOKIE_NAME in auth_cookie_probe.json()["cookieNames"]

    # Verify logout Set-Cookie headers clear all 3 cookies with Max-Age=0
    logout_resp = other_org_client.post(
        "/api/v1/auth/logout",
        headers=_csrf_headers(other_org_client),
    )
    assert logout_resp.status_code == 204
    cleared_headers = "\n".join(logout_resp.headers.get_list("set-cookie"))
    for cookie_name in (ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME, CSRF_COOKIE_NAME):
        assert f"{cookie_name}=" in cleared_headers
    assert "max-age=0" in cleared_headers.lower()

    # Transaction rollback atomicity: failure on audit write during registration rolls back User/Org/WS
    import app.services.auth_service as auth_service_mod

    def _boom_audit(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated audit failure mid-registration")

    monkeypatch.setattr(auth_service_mod, "record_audit_event", _boom_audit)
    rollback_client = make_client(raise_server_exceptions=False)
    rollback_email = f"rollback.{uuid.uuid4().hex[:8]}@example.invalid"
    fail_resp = rollback_client.post(
        "/api/v1/auth/register",
        json={
            "email": rollback_email,
            "password": "StrongPractice!2026",
            "fullName": "Rollback Test",
            "organizationName": f"Rollback Firm {uuid.uuid4().hex[:6]}",
        },
    )
    assert fail_resp.status_code == 500
    assert fail_resp.json()["error"]["code"] == "INTERNAL_ERROR"
    assert fail_resp.json()["error"]["requestId"]
    assert db_session.scalar(select(User).where(User.email == rollback_email)) is None


# ---------------------------------------------------------------------------
# Batch 2.2 security, anti-orphan, lock-order & concurrency regression tests
# ---------------------------------------------------------------------------


def test_prevent_orphaned_workspaces_when_suspending_or_removing_org_member(
    make_client: Callable[..., TestClient],
) -> None:
    owner_client = make_client()
    owner_reg = _register_user(
        owner_client, prefix="orphan_owner", org_name="Anti Orphan Practice"
    )
    org_id = owner_reg["organization"]["id"]

    # Owner provisions a dedicated second workspace and hands admin control to Member B
    ws2_resp = owner_client.post(
        f"/api/v1/organizations/{org_id}/workspaces",
        headers=_csrf_headers(owner_client),
        json={
            "name": "Client Ledger Co",
            "workspaceCode": f"WS-ORPH-{uuid.uuid4().hex[:6]}",
            "legalEntityName": "Client Ledger Private Limited",
        },
    )
    assert ws2_resp.status_code == 201
    ws2_id = ws2_resp.json()["workspace"]["id"]

    member_b_client = make_client()
    member_b_reg = _register_user(member_b_client, prefix="orphan_adm_b")
    member_b_email = member_b_reg["user"]["email"]
    _onboard_user_to_org(
        owner_client,
        org_id=org_id,
        member_client=member_b_client,
        email=member_b_email,
    )

    add_b = owner_client.post(
        f"/api/v1/workspaces/{ws2_id}/memberships",
        headers=_csrf_headers(owner_client),
        json={"email": member_b_email, "role": "WORKSPACE_ADMIN"},
    )
    assert add_b.status_code == 201

    ws2_members = owner_client.get(f"/api/v1/workspaces/{ws2_id}/memberships").json()["items"]
    owner_ws2_mem_id = next(
        m["id"] for m in ws2_members if m["email"] == owner_reg["user"]["email"]
    )
    assert (
        owner_client.delete(
            f"/api/v1/workspaces/{ws2_id}/memberships/{owner_ws2_mem_id}",
            headers=_csrf_headers(owner_client),
        ).status_code
        == 204
    )

    # Member B is now the sole active WORKSPACE_ADMIN on ws2
    org_members = owner_client.get(
        f"/api/v1/organizations/{org_id}/memberships"
    ).json()["items"]
    member_b_org_mem_id = next(
        m["id"] for m in org_members if m["email"] == member_b_email
    )

    suspend_resp = owner_client.patch(
        f"/api/v1/organizations/{org_id}/memberships/{member_b_org_mem_id}",
        headers=_csrf_headers(owner_client),
        json={"status": "SUSPENDED"},
    )
    assert suspend_resp.status_code == 409
    assert suspend_resp.json()["error"]["code"] == "CANNOT_ORPHAN_WORKSPACE_ADMIN"
    assert ws2_id in suspend_resp.json()["error"]["details"]["workspaceIds"]

    delete_resp = owner_client.delete(
        f"/api/v1/organizations/{org_id}/memberships/{member_b_org_mem_id}",
        headers=_csrf_headers(owner_client),
    )
    assert delete_resp.status_code == 409
    assert delete_resp.json()["error"]["code"] == "CANNOT_ORPHAN_WORKSPACE_ADMIN"

    # Member B remains active and retains workspace access
    assert member_b_client.get(f"/api/v1/workspaces/{ws2_id}").status_code == 200

    # Hand off / add a second active WORKSPACE_ADMIN (Member C) to ws2
    member_c_client = make_client()
    member_c_reg = _register_user(member_c_client, prefix="orphan_adm_c")
    member_c_email = member_c_reg["user"]["email"]
    _onboard_user_to_org(
        owner_client,
        org_id=org_id,
        member_client=member_c_client,
        email=member_c_email,
    )
    add_c = member_b_client.post(
        f"/api/v1/workspaces/{ws2_id}/memberships",
        headers=_csrf_headers(member_b_client),
        json={"email": member_c_email, "role": "WORKSPACE_ADMIN"},
    )
    assert add_c.status_code == 201

    # Now suspending and removing Member B succeeds while Member C & Org Owner stay consistent
    suspend_ok = owner_client.patch(
        f"/api/v1/organizations/{org_id}/memberships/{member_b_org_mem_id}",
        headers=_csrf_headers(owner_client),
        json={"status": "SUSPENDED"},
    )
    assert suspend_ok.status_code == 200
    assert member_b_client.get("/api/v1/auth/me").status_code == 401
    assert member_c_client.get(f"/api/v1/workspaces/{ws2_id}").status_code == 200

    remove_ok = owner_client.delete(
        f"/api/v1/organizations/{org_id}/memberships/{member_b_org_mem_id}",
        headers=_csrf_headers(owner_client),
    )
    assert remove_ok.status_code == 204
    assert member_c_client.get(f"/api/v1/workspaces/{ws2_id}").status_code == 200
    assert owner_client.get(f"/api/v1/organizations/{org_id}/memberships").status_code == 200


def test_concurrent_invitation_acceptance_and_recreation_lock_order_on_postgresql(
    make_client: Callable[..., TestClient],
    db_session: Session,
) -> None:
    owner_client = make_client()
    owner_reg = _register_user(
        owner_client, prefix="inv_conc_owner", org_name="Concurrent Invites Firm"
    )
    org_id = owner_reg["organization"]["id"]

    # 1. Two concurrent accept requests using the same invitation token -> [200, 409]
    invitee_client_a = make_client()
    invitee_reg = _register_user(invitee_client_a, prefix="inv_conc_user")
    invitee_email = invitee_reg["user"]["email"]

    invitee_client_b = make_client()
    assert (
        invitee_client_b.post(
            "/api/v1/auth/login",
            json={"email": invitee_email, "password": "StrongPractice!2026"},
        ).status_code
        == 200
    )

    inv_resp = owner_client.post(
        f"/api/v1/organizations/{org_id}/invitations",
        headers=_csrf_headers(owner_client),
        json={"email": invitee_email, "role": "ORG_MEMBER"},
    )
    assert inv_resp.status_code == 201
    raw_token = inv_resp.json()["inviteToken"]

    accept_barrier = threading.Barrier(2)

    def _accept(client: TestClient) -> tuple[int, str | None]:
        accept_barrier.wait(timeout=5)
        resp = client.post(
            "/api/v1/organizations/invitations/accept",
            headers=_csrf_headers(client),
            json={"token": raw_token},
        )
        code = resp.json()["error"]["code"] if resp.status_code >= 400 else None
        return resp.status_code, code

    with ThreadPoolExecutor(max_workers=2) as pool:
        r1 = pool.submit(_accept, invitee_client_a)
        r2 = pool.submit(_accept, invitee_client_b)
        results = sorted([r1.result(timeout=15), r2.result(timeout=15)])

    assert results == [(200, None), (409, "INVITATION_EXPIRED_OR_USED")]
    mem_rows = list(
        db_session.scalars(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == uuid.UUID(org_id),
                OrganizationMembership.user_id == uuid.UUID(invitee_reg["user"]["id"]),
            )
        )
    )
    assert len(mem_rows) == 1

    # 2. Invitation re-creation racing with acceptance (Organization -> OrganizationInvitation lock order)
    for round_idx in range(3):
        racer_client = make_client()
        racer_email = _register_user(
            racer_client, prefix=f"inv_race_{round_idx}"
        )["user"]["email"]
        seed_inv = owner_client.post(
            f"/api/v1/organizations/{org_id}/invitations",
            headers=_csrf_headers(owner_client),
            json={"email": racer_email, "role": "ORG_MEMBER"},
        )
        assert seed_inv.status_code == 201
        seed_token = seed_inv.json()["inviteToken"]

        race_barrier = threading.Barrier(2)

        def _recreate() -> int:
            race_barrier.wait(timeout=5)
            return owner_client.post(
                f"/api/v1/organizations/{org_id}/invitations",
                headers=_csrf_headers(owner_client),
                json={"email": racer_email, "role": "ORG_ADMIN"},
            ).status_code

        def _accept_seed() -> int:
            race_barrier.wait(timeout=5)
            return racer_client.post(
                "/api/v1/organizations/invitations/accept",
                headers=_csrf_headers(racer_client),
                json={"token": seed_token},
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            f_create = pool.submit(_recreate)
            f_accept = pool.submit(_accept_seed)
            create_status = f_create.result(timeout=15)
            accept_status = f_accept.result(timeout=15)

        assert create_status == 201
        assert accept_status in (200, 409)


def test_concurrent_duplicate_email_and_workspace_membership_races_on_postgresql(
    make_client: Callable[..., TestClient],
) -> None:
    # 1. Concurrent duplicate email registration -> [201, 409] without 500
    reg_a = make_client()
    reg_b = make_client()
    shared_email = f"dup.conc.{uuid.uuid4().hex[:8]}@example.invalid"
    reg_barrier = threading.Barrier(2)

    def _submit_reg(client: TestClient, org_suffix: str) -> tuple[int, str | None]:
        reg_barrier.wait(timeout=5)
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "email": shared_email,
                "password": "StrongPractice!2026",
                "fullName": "Concurrent Registrar",
                "organizationName": f"Concurrent Reg Firm {org_suffix}",
            },
        )
        code = resp.json()["error"]["code"] if resp.status_code >= 400 else None
        return resp.status_code, code

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_reg_a = pool.submit(_submit_reg, reg_a, "A")
        f_reg_b = pool.submit(_submit_reg, reg_b, "B")
        reg_results = sorted([f_reg_a.result(timeout=15), f_reg_b.result(timeout=15)])

    assert reg_results == [(201, None), (409, "EMAIL_ALREADY_EXISTS")]

    # 2. Concurrent duplicate workspace membership addition -> [201, 409] without 500
    admin_one = make_client()
    admin_reg = _register_user(
        admin_one, prefix="ws_dup_adm1", org_name="Workspace Race Practice"
    )
    org_id = admin_reg["organization"]["id"]
    ws_id = admin_reg["workspace"]["workspaceId"]
    admin_email = admin_reg["user"]["email"]

    admin_two = make_client()
    assert (
        admin_two.post(
            "/api/v1/auth/login",
            json={"email": admin_email, "password": "StrongPractice!2026"},
        ).status_code
        == 200
    )

    collab_client = make_client()
    collab_email = _register_user(collab_client, prefix="ws_dup_collab")["user"]["email"]
    _onboard_user_to_org(
        admin_one,
        org_id=org_id,
        member_client=collab_client,
        email=collab_email,
    )

    ws_barrier = threading.Barrier(2)

    def _add_ws_mem(client: TestClient) -> tuple[int, str | None]:
        ws_barrier.wait(timeout=5)
        resp = client.post(
            f"/api/v1/workspaces/{ws_id}/memberships",
            headers=_csrf_headers(client),
            json={"email": collab_email, "role": "REVIEWER"},
        )
        code = resp.json()["error"]["code"] if resp.status_code >= 400 else None
        return resp.status_code, code

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_ws1 = pool.submit(_add_ws_mem, admin_one)
        f_ws2 = pool.submit(_add_ws_mem, admin_two)
        ws_results = sorted([f_ws1.result(timeout=15), f_ws2.result(timeout=15)])

    assert ws_results == [(201, None), (409, "MEMBERSHIP_ALREADY_EXISTS")]


def test_cross_ip_account_lockout_prevention_and_trusted_proxy_headers(
    pg_test_url: str,
) -> None:
    clean_engine = create_engine(pg_test_url, pool_pre_ping=True)
    with clean_engine.begin() as conn:
        conn.execute(text("DELETE FROM auth_rate_limit_buckets"))
    clean_engine.dispose()

    proxy_settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=pg_test_url,
        jwt_secret_key=TEST_JWT_SECRET,
        cookie_secure=False,
        cors_origins=["http://localhost:3000"],
        trusted_proxies=["10.0.0.0/8"],
        rate_limit_enabled=True,
        rate_limit_window_seconds=60,
        login_rate_limit_max_attempts=2,
        register_rate_limit_max_attempts=20,
        refresh_rate_limit_max_attempts=20,
    )

    class _PeerIpAsgiWrapper:
        def __init__(self, inner_app: object, peer_ip: str) -> None:
            self._inner_app = inner_app
            self._peer_ip = peer_ip

        async def __call__(self, scope: dict, receive: object, send: object) -> None:
            if scope.get("type") == "http":
                patched = dict(scope)
                patched["client"] = (self._peer_ip, 50000)
                await self._inner_app(patched, receive, send)  # type: ignore[misc]
                return
            await self._inner_app(scope, receive, send)  # type: ignore[misc]

    app = create_app(proxy_settings)
    with TestClient(app):
        trusted_proxy_client = TestClient(_PeerIpAsgiWrapper(app, "10.0.0.5"))
        victim_reg = _register_user(trusted_proxy_client, prefix="victim_rl")
        victim_email = victim_reg["user"]["email"]

        # Attacker IP 203.0.113.10 (behind trusted proxy 10.0.0.5) exhausts login limit
        for _ in range(2):
            bad = trusted_proxy_client.post(
                "/api/v1/auth/login",
                headers={"X-Forwarded-For": "203.0.113.10"},
                json={"email": victim_email, "password": "WrongPassword!2026"},
            )
            assert bad.status_code == 401

        attacker_blocked = trusted_proxy_client.post(
            "/api/v1/auth/login",
            headers={"X-Forwarded-For": "203.0.113.10"},
            json={"email": victim_email, "password": "WrongPassword!2026"},
        )
        assert attacker_blocked.status_code == 429
        assert attacker_blocked.json()["error"]["code"] == "RATE_LIMITED"
        assert int(attacker_blocked.headers["Retry-After"]) >= 1

        # Legitimate user from another IP 198.51.100.25 MUST NOT be locked out
        legit_login = trusted_proxy_client.post(
            "/api/v1/auth/login",
            headers={"X-Forwarded-For": "198.51.100.25"},
            json={"email": victim_email, "password": "StrongPractice!2026"},
        )
        assert legit_login.status_code == 200

        # Untrusted direct peer 198.51.100.99 cannot bypass rate limits by spoofing X-Forwarded-For
        untrusted_client = TestClient(_PeerIpAsgiWrapper(app, "198.51.100.99"))
        for spoof_idx in range(2):
            resp = untrusted_client.post(
                "/api/v1/auth/login",
                headers={"X-Forwarded-For": f"203.0.113.{200 + spoof_idx}"},
                json={"email": victim_email, "password": "WrongPassword!2026"},
            )
            assert resp.status_code == 401

        spoof_blocked = untrusted_client.post(
            "/api/v1/auth/login",
            headers={"X-Forwarded-For": "203.0.113.250"},
            json={"email": victim_email, "password": "WrongPassword!2026"},
        )
        assert spoof_blocked.status_code == 429


def test_rate_limiter_database_failure_fails_closed_without_secret_leak(
    pg_test_url: str,
) -> None:
    from sqlalchemy.exc import OperationalError

    rl_settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=pg_test_url,
        jwt_secret_key=TEST_JWT_SECRET,
        cookie_secure=False,
        cors_origins=["http://localhost:3000"],
        rate_limit_enabled=True,
    )
    app = create_app(rl_settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        class _FailingRateLimitSession:
            def __enter__(self) -> _FailingRateLimitSession:
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def execute(self, *args: object, **kwargs: object) -> object:
                raise OperationalError(
                    "INSERT INTO auth_rate_limit_buckets",
                    {},
                    Exception("FATAL: supersecret_rl_db_password"),
                )

        app.state.session_factory = lambda: _FailingRateLimitSession()

        resp = client.post(
            "/api/v1/auth/login",
            json={
                "email": "someone@example.invalid",
                "password": "StrongPractice!2026",
            },
        )
        assert resp.status_code == 500
        body = resp.json()
        assert body["error"]["code"] == "INTERNAL_ERROR"
        assert body["error"]["requestId"]
        assert "supersecret_rl_db_password" not in resp.text
        assert ACCESS_COOKIE_NAME not in resp.headers.get("set-cookie", "")


