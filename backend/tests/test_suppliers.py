from __future__ import annotations

import os
import threading
import uuid
from collections.abc import Callable, Generator
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import date
from decimal import Decimal
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.cookies import CSRF_COOKIE_NAME
from app.main import create_app
from app.models.accounting import Invoice, Supplier
from app.models.review import AuditEvent
from app.models.tenancy import utc_now
from app.schemas.suppliers import (
    SupplierCreateRequest,
    SupplierSummaryDto,
    SupplierUpdateRequest,
    normalize_supplier_name,
)
from tests.conftest import TEST_JWT_SECRET
from tests.test_migrations import (
    ALLOWED_POSTGRES_SCHEMES,
    APPROVED_TEST_HOSTS,
    REQUIRED_TEST_DATABASE_NAME,
    MigrationTestSafetyError,
)

# ---------------------------------------------------------------------------
# Offline schema & normalization unit tests (run even without PostgreSQL)
# ---------------------------------------------------------------------------


def test_supplier_name_normalization_and_field_validation() -> None:
    assert (
        normalize_supplier_name("  Apex   Industrial \t Components   Pvt. Ltd.  ")
        == "apex industrial components pvt. ltd."
    )

    with pytest.raises(ValueError, match="blank"):
        normalize_supplier_name("    \t\n  ")

    req = SupplierCreateRequest(
        name="  Vindhya   Cloud   Services ",
        gstin=" 29aaacv9102k1z8 ",
        pan=" aaacv9102k ",
        stateCode="29",
        stateName="  Karnataka  ",
        category="  IT  &  Cloud  ",
        email="  Billing@VindhyaCloud.Example ",
    )
    assert req.name == "Vindhya Cloud Services"
    assert req.gstin == "29AAACV9102K1Z8"
    assert req.pan == "AAACV9102K"
    assert req.state_code == "29"
    assert req.state_name == "Karnataka"
    assert req.category == "IT & Cloud"
    assert req.email == "billing@vindhyacloud.example"
    assert req.status == "NEEDS_VERIFICATION"


def test_supplier_schema_rejects_invalid_tax_ids_extra_keys_and_non_nullable_nulls() -> None:
    with pytest.raises(ValidationError, match="gstin"):
        SupplierCreateRequest(name="Bad GSTIN Vendor", gstin="INVALID12345678")

    with pytest.raises(ValidationError, match="pan"):
        SupplierCreateRequest(name="Bad PAN Vendor", pan="BADPAN1234")

    with pytest.raises(ValidationError, match="stateCode"):
        SupplierCreateRequest(name="Bad State Vendor", stateCode="MH")

    # Immutable / internal fields rejected via extra="forbid"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SupplierCreateRequest(name="Vendor", workspaceId=str(uuid.uuid4()))

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SupplierUpdateRequest(normalizedName="forced-override")

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SupplierUpdateRequest(id=str(uuid.uuid4()))

    # Non-nullable PATCH fields reject explicit null; nullable fields allow null
    for field_key in ("name", "category", "status"):
        with pytest.raises(ValidationError, match="cannot be null"):
            SupplierUpdateRequest.model_validate({field_key: None})

    with pytest.raises(ValidationError, match="At least one field"):
        SupplierUpdateRequest()

    cleared = SupplierUpdateRequest(gstin=None, pan=None, stateCode=None, email=None)
    assert cleared.gstin is None
    assert cleared.pan is None
    assert cleared.state_code is None
    assert cleared.email is None


def test_supplier_summary_dto_serializes_decimal_total_as_two_decimal_string() -> None:
    now = utc_now()
    dto = SupplierSummaryDto(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        name="Acme Logistics",
        normalized_name="acme logistics",
        gstin="27AABCA4821M1Z4",
        pan="AABCA4821M",
        state_code="27",
        state_name="Maharashtra",
        category="Logistics",
        email="ap@acme.example",
        status="VERIFIED",
        created_at=now,
        updated_at=now,
        total_invoices=3,
        total_value=Decimal("147500.5"),
        last_invoice_date=date(2026, 11, 14),
    )
    dumped = dto.model_dump(by_alias=True)
    assert dumped["totalValue"] == "147500.50"
    assert dumped["totalInvoices"] == 3
    assert dumped["normalizedName"] == "acme logistics"


# ---------------------------------------------------------------------------
# PostgreSQL 16 integration fixtures
# ---------------------------------------------------------------------------


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
            "TEST_DATABASE_URL is not set; skipping PostgreSQL suppliers integration tests."
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


def _onboard_to_workspace(
    admin_client: TestClient,
    *,
    org_id: str,
    workspace_id: str,
    member_client: TestClient,
    member_email: str,
    workspace_role: str,
) -> None:
    invite_resp = admin_client.post(
        f"/api/v1/organizations/{org_id}/invitations",
        headers=_csrf_headers(admin_client),
        json={"email": member_email, "role": "ORG_MEMBER"},
    )
    assert invite_resp.status_code == 201, invite_resp.text
    raw_token = invite_resp.json()["inviteToken"]

    accept_resp = member_client.post(
        "/api/v1/organizations/invitations/accept",
        headers=_csrf_headers(member_client),
        json={"token": raw_token},
    )
    assert accept_resp.status_code == 200, accept_resp.text

    mem_resp = admin_client.post(
        f"/api/v1/workspaces/{workspace_id}/memberships",
        headers=_csrf_headers(admin_client),
        json={"email": member_email, "role": workspace_role},
    )
    assert mem_resp.status_code == 201, mem_resp.text


# ---------------------------------------------------------------------------
# PostgreSQL 16 Suppliers Master integration tests
# ---------------------------------------------------------------------------


def test_supplier_crud_search_filter_pagination_and_audit(
    make_client: Callable[..., TestClient],
    db_session: Session,
) -> None:
    admin_client = make_client()
    uid = uuid.uuid4().hex[:8]
    reg = _register_user(admin_client, prefix="sup_crud", org_name=f"Vendor Firm {uid}")
    ws_id = reg["workspace"]["workspaceId"]

    # 1. Create suppliers
    create_1 = admin_client.post(
        f"/api/v1/workspaces/{ws_id}/suppliers",
        headers=_csrf_headers(admin_client),
        json={
            "name": "  Apex   Industrial Components Pvt. Ltd.  ",
            "gstin": "27aabca4821m1z4",
            "pan": "aabca4821m",
            "stateCode": "27",
            "stateName": "Maharashtra",
            "category": "Manufacturing & Spares",
            "email": "Accounts@ApexIndustrial.Example",
            "status": "VERIFIED",
        },
    )
    assert create_1.status_code == 201, create_1.text
    s1 = create_1.json()
    assert s1["name"] == "Apex Industrial Components Pvt. Ltd."
    assert s1["normalizedName"] == "apex industrial components pvt. ltd."
    assert s1["gstin"] == "27AABCA4821M1Z4"
    assert s1["pan"] == "AABCA4821M"
    assert s1["email"] == "accounts@apexindustrial.example"
    assert s1["status"] == "VERIFIED"

    create_2 = admin_client.post(
        f"/api/v1/workspaces/{ws_id}/suppliers",
        headers=_csrf_headers(admin_client),
        json={
            "name": "Brahmaputra Logistics_50% LLP",
            "gstin": "24AABFN3319P1Z2",
            "stateCode": "24",
            "stateName": "Gujarat",
            "category": "Logistics & Packaging",
            "status": "FLAGGED",
        },
    )
    assert create_2.status_code == 201, create_2.text
    s2 = create_2.json()

    create_3 = admin_client.post(
        f"/api/v1/workspaces/{ws_id}/suppliers",
        headers=_csrf_headers(admin_client),
        json={
            "name": "Chambal Office Unregistered Traders",
            "category": "Stationery",
        },
    )
    assert create_3.status_code == 201, create_3.text
    s3 = create_3.json()
    assert s3["gstin"] is None
    assert s3["status"] == "NEEDS_VERIFICATION"

    # Second unregistered supplier with gstin=None succeeds in same workspace
    create_4 = admin_client.post(
        f"/api/v1/workspaces/{ws_id}/suppliers",
        headers=_csrf_headers(admin_client),
        json={
            "name": "Deccan Unregistered Supplies",
            "gstin": None,
        },
    )
    assert create_4.status_code == 201, create_4.text

    # 2. Listing & pagination
    page1 = admin_client.get(
        f"/api/v1/workspaces/{ws_id}/suppliers",
        params={"page": 1, "pageSize": 2},
    )
    assert page1.status_code == 200, page1.text
    p1_body = page1.json()
    assert p1_body["total"] == 4
    assert p1_body["page"] == 1
    assert p1_body["pageSize"] == 2
    assert len(p1_body["items"]) == 2
    assert [item["name"] for item in p1_body["items"]] == [
        "Apex Industrial Components Pvt. Ltd.",
        "Brahmaputra Logistics_50% LLP",
    ]
    assert p1_body["items"][0]["totalInvoices"] == 0
    assert p1_body["items"][0]["totalValue"] == "0.00"
    assert p1_body["items"][0]["lastInvoiceDate"] is None

    page2 = admin_client.get(
        f"/api/v1/workspaces/{ws_id}/suppliers",
        params={"page": 2, "pageSize": 2},
    )
    assert page2.status_code == 200
    assert [item["name"] for item in page2.json()["items"]] == [
        "Chambal Office Unregistered Traders",
        "Deccan Unregistered Supplies",
    ]

    # 3. Search (including literal %/_ escaping) & status filter
    search_gstin = admin_client.get(
        f"/api/v1/workspaces/{ws_id}/suppliers",
        params={"search": "AABCA4821"},
    )
    assert search_gstin.status_code == 200
    assert search_gstin.json()["total"] == 1
    assert search_gstin.json()["items"][0]["id"] == s1["id"]

    # Literal '%' must NOT act as wildcard matching all suppliers
    search_percent = admin_client.get(
        f"/api/v1/workspaces/{ws_id}/suppliers",
        params={"search": "_50%"},
    )
    assert search_percent.status_code == 200
    assert search_percent.json()["total"] == 1
    assert search_percent.json()["items"][0]["id"] == s2["id"]

    filter_flagged = admin_client.get(
        f"/api/v1/workspaces/{ws_id}/suppliers",
        params={"status": "FLAGGED"},
    )
    assert filter_flagged.status_code == 200
    assert filter_flagged.json()["total"] == 1
    assert filter_flagged.json()["items"][0]["id"] == s2["id"]

    filter_verified = admin_client.get(
        f"/api/v1/workspaces/{ws_id}/suppliers",
        params={"status": "VERIFIED"},
    )
    assert filter_verified.status_code == 200
    assert filter_verified.json()["total"] == 1
    assert filter_verified.json()["items"][0]["id"] == s1["id"]

    invalid_filter = admin_client.get(
        f"/api/v1/workspaces/{ws_id}/suppliers",
        params={"status": "UNKNOWN_STATUS"},
    )
    assert invalid_filter.status_code == 422

    # 4. Detail endpoint
    detail_resp = admin_client.get(
        f"/api/v1/workspaces/{ws_id}/suppliers/{s1['id']}"
    )
    assert detail_resp.status_code == 200, detail_resp.text
    assert detail_resp.json()["id"] == s1["id"]
    assert detail_resp.json()["totalInvoices"] == 0
    assert detail_resp.json()["totalValue"] == "0.00"
    assert detail_resp.json()["lastInvoiceDate"] is None

    # 5. Update supplier (recalculates normalizedName; forbids id/workspaceId changes)
    patch_resp = admin_client.patch(
        f"/api/v1/workspaces/{ws_id}/suppliers/{s3['id']}",
        headers=_csrf_headers(admin_client),
        json={
            "name": "  Chambal   Modern Office Co. ",
            "status": "VERIFIED",
            "email": "desk@chambal.example",
        },
    )
    assert patch_resp.status_code == 200, patch_resp.text
    patched = patch_resp.json()
    assert patched["name"] == "Chambal Modern Office Co."
    assert patched["normalizedName"] == "chambal modern office co."
    assert patched["status"] == "VERIFIED"
    assert patched["email"] == "desk@chambal.example"

    forbidden_patch = admin_client.patch(
        f"/api/v1/workspaces/{ws_id}/suppliers/{s3['id']}",
        headers=_csrf_headers(admin_client),
        json={"workspaceId": str(uuid.uuid4())},
    )
    assert forbidden_patch.status_code == 422

    # 6. Audit events created and non-leaky (both DB and API endpoint)
    audit_events = list(
        db_session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.workspace_id == uuid.UUID(ws_id),
                AuditEvent.entity_type == "supplier",
            )
            .order_by(AuditEvent.created_at.asc())
        )
    )
    event_types = [ev.event_type for ev in audit_events]
    assert event_types.count("supplier.created") == 4
    assert event_types.count("supplier.updated") == 1
    update_ev = next(ev for ev in audit_events if ev.event_type == "supplier.updated")
    assert update_ev.entity_id == uuid.UUID(s3["id"])
    assert set(update_ev.event_metadata["updatedFields"]) == {"name", "status", "email"}
    assert "desk@chambal.example" not in update_ev.summary
    assert "desk@chambal.example" not in str(update_ev.event_metadata)

    audit_api_resp = admin_client.get(
        f"/api/v1/workspaces/{ws_id}/audit-events",
        params={"entityType": "supplier"},
    )
    assert audit_api_resp.status_code == 200
    assert audit_api_resp.json()["total"] == 5


def test_supplier_uniqueness_and_multi_workspace_isolation(
    make_client: Callable[..., TestClient],
) -> None:
    client_a = make_client()
    client_b = make_client()
    uid = uuid.uuid4().hex[:8]

    reg_a = _register_user(client_a, prefix="iso_a", org_name=f"Practice A {uid}")
    org_a_id = reg_a["organization"]["id"]
    ws_a1_id = reg_a["workspace"]["workspaceId"]

    # Second workspace in the same organization
    ws_a2_resp = client_a.post(
        f"/api/v1/organizations/{org_a_id}/workspaces",
        headers=_csrf_headers(client_a),
        json={
            "name": "Client Beta",
            "workspaceCode": f"BETA-{uid}".upper(),
            "legalEntityName": "Client Beta Pvt Ltd",
        },
    )
    assert ws_a2_resp.status_code == 201, ws_a2_resp.text
    ws_a2_id = ws_a2_resp.json()["workspace"]["id"]

    # Completely separate tenant
    reg_b = _register_user(client_b, prefix="iso_b", org_name=f"Practice B {uid}")
    ws_b_id = reg_b["workspace"]["workspaceId"]

    sup_a1 = client_a.post(
        f"/api/v1/workspaces/{ws_a1_id}/suppliers",
        headers=_csrf_headers(client_a),
        json={
            "name": "Kaveri Paper Solutions",
            "gstin": "33AAACK8812R1Z9",
        },
    )
    assert sup_a1.status_code == 201
    sup_a1_id = sup_a1.json()["id"]

    sup_a1_other = client_a.post(
        f"/api/v1/workspaces/{ws_a1_id}/suppliers",
        headers=_csrf_headers(client_a),
        json={
            "name": "Narmada Freight LLP",
            "gstin": "24AABFN3319P1Z2",
        },
    )
    assert sup_a1_other.status_code == 201
    sup_a1_other_id = sup_a1_other.json()["id"]

    # Duplicate normalized name (different casing & whitespace) in same workspace -> 409
    dup_name = client_a.post(
        f"/api/v1/workspaces/{ws_a1_id}/suppliers",
        headers=_csrf_headers(client_a),
        json={
            "name": "  kaveri   PAPER  solutions  ",
            "gstin": "33AAACK8812R1Z8",
        },
    )
    assert dup_name.status_code == 409
    assert dup_name.json()["error"]["code"] == "SUPPLIER_NAME_EXISTS"

    # Duplicate GSTIN in same workspace -> 409
    dup_gstin = client_a.post(
        f"/api/v1/workspaces/{ws_a1_id}/suppliers",
        headers=_csrf_headers(client_a),
        json={
            "name": "Completely Different Name",
            "gstin": "33aaack8812r1z9",
        },
    )
    assert dup_gstin.status_code == 409
    assert dup_gstin.json()["error"]["code"] == "SUPPLIER_GSTIN_EXISTS"

    # PATCH collisions on normalizedName and GSTIN -> 409
    patch_dup_name = client_a.patch(
        f"/api/v1/workspaces/{ws_a1_id}/suppliers/{sup_a1_other_id}",
        headers=_csrf_headers(client_a),
        json={"name": "  KAVERI   paper  SOLUTIONS "},
    )
    assert patch_dup_name.status_code == 409
    assert patch_dup_name.json()["error"]["code"] == "SUPPLIER_NAME_EXISTS"

    patch_dup_gstin = client_a.patch(
        f"/api/v1/workspaces/{ws_a1_id}/suppliers/{sup_a1_other_id}",
        headers=_csrf_headers(client_a),
        json={"gstin": "33AAACK8812R1Z9"},
    )
    assert patch_dup_gstin.status_code == 409
    assert patch_dup_gstin.json()["error"]["code"] == "SUPPLIER_GSTIN_EXISTS"

    # Identical supplier name AND GSTIN allowed in separate workspaces (same org & foreign org)
    same_in_ws_a2 = client_a.post(
        f"/api/v1/workspaces/{ws_a2_id}/suppliers",
        headers=_csrf_headers(client_a),
        json={"name": "Kaveri Paper Solutions", "gstin": "33AAACK8812R1Z9"},
    )
    assert same_in_ws_a2.status_code == 201
    sup_a2_id = same_in_ws_a2.json()["id"]

    same_in_ws_b = client_b.post(
        f"/api/v1/workspaces/{ws_b_id}/suppliers",
        headers=_csrf_headers(client_b),
        json={"name": "Kaveri Paper Solutions", "gstin": "33AAACK8812R1Z9"},
    )
    assert same_in_ws_b.status_code == 201
    sup_b_id = same_in_ws_b.json()["id"]

    # Cross-workspace access must uniformly return 404 (never leak existence across workspaces)
    assert (
        client_a.get(
            f"/api/v1/workspaces/{ws_a1_id}/suppliers/{sup_a2_id}"
        ).status_code
        == 404
    )
    assert (
        client_a.get(
            f"/api/v1/workspaces/{ws_a1_id}/suppliers/{sup_b_id}"
        ).status_code
        == 404
    )
    assert (
        client_a.patch(
            f"/api/v1/workspaces/{ws_a1_id}/suppliers/{sup_a2_id}",
            headers=_csrf_headers(client_a),
            json={"status": "VERIFIED"},
        ).status_code
        == 404
    )
    assert (
        client_b.get(f"/api/v1/workspaces/{ws_a1_id}/suppliers").status_code == 404
    )
    assert (
        client_b.get(
            f"/api/v1/workspaces/{ws_a1_id}/suppliers/{sup_a1_id}"
        ).status_code
        == 404
    )
    assert (
        client_b.post(
            f"/api/v1/workspaces/{ws_a1_id}/suppliers",
            headers=_csrf_headers(client_b),
            json={"name": "Cross Tenant Inject"},
        ).status_code
        == 404
    )
    assert (
        client_b.patch(
            f"/api/v1/workspaces/{ws_a1_id}/suppliers/{sup_a1_id}",
            headers=_csrf_headers(client_b),
            json={"status": "FLAGGED"},
        ).status_code
        == 404
    )


def test_supplier_rbac_roles_and_csrf_protection(
    make_client: Callable[..., TestClient],
) -> None:
    admin_client = make_client()
    reviewer_client = make_client()
    uploader_client = make_client()
    viewer_client = make_client()
    uid = uuid.uuid4().hex[:8]

    reg_admin = _register_user(
        admin_client, prefix="sup_admin", org_name=f"RBAC Firm {uid}"
    )
    org_id = reg_admin["organization"]["id"]
    ws_id = reg_admin["workspace"]["workspaceId"]

    reg_rev = _register_user(reviewer_client, prefix="sup_rev", full_name="Reviewer")
    reg_upl = _register_user(uploader_client, prefix="sup_upl", full_name="Uploader")
    reg_view = _register_user(viewer_client, prefix="sup_view", full_name="Viewer")

    _onboard_to_workspace(
        admin_client,
        org_id=org_id,
        workspace_id=ws_id,
        member_client=reviewer_client,
        member_email=reg_rev["user"]["email"],
        workspace_role="REVIEWER",
    )
    _onboard_to_workspace(
        admin_client,
        org_id=org_id,
        workspace_id=ws_id,
        member_client=uploader_client,
        member_email=reg_upl["user"]["email"],
        workspace_role="UPLOADER",
    )
    _onboard_to_workspace(
        admin_client,
        org_id=org_id,
        workspace_id=ws_id,
        member_client=viewer_client,
        member_email=reg_view["user"]["email"],
        workspace_role="VIEWER",
    )

    # CSRF protection enforced on POST & PATCH
    no_csrf_post = admin_client.post(
        f"/api/v1/workspaces/{ws_id}/suppliers",
        json={"name": "Missing CSRF Vendor"},
    )
    assert no_csrf_post.status_code == 403
    assert no_csrf_post.json()["error"]["code"] == "CSRF_TOKEN_INVALID"

    bad_origin_post = admin_client.post(
        f"/api/v1/workspaces/{ws_id}/suppliers",
        headers=_csrf_headers(admin_client, origin="https://evil.attacker.invalid"),
        json={"name": "Bad Origin Vendor"},
    )
    assert bad_origin_post.status_code == 403
    assert bad_origin_post.json()["error"]["code"] == "CSRF_TOKEN_INVALID"

    # WORKSPACE_ADMIN creates supplier
    admin_create = admin_client.post(
        f"/api/v1/workspaces/{ws_id}/suppliers",
        headers=_csrf_headers(admin_client),
        json={"name": "Admin Created Supplier"},
    )
    assert admin_create.status_code == 201
    sup_id = admin_create.json()["id"]

    # REVIEWER creates & updates suppliers
    rev_create = reviewer_client.post(
        f"/api/v1/workspaces/{ws_id}/suppliers",
        headers=_csrf_headers(reviewer_client),
        json={"name": "Reviewer Created Supplier"},
    )
    assert rev_create.status_code == 201
    rev_sup_id = rev_create.json()["id"]

    rev_patch = reviewer_client.patch(
        f"/api/v1/workspaces/{ws_id}/suppliers/{sup_id}",
        headers=_csrf_headers(reviewer_client),
        json={"status": "VERIFIED"},
    )
    assert rev_patch.status_code == 200
    assert rev_patch.json()["status"] == "VERIFIED"

    # CSRF protection on PATCH
    no_csrf_patch = reviewer_client.patch(
        f"/api/v1/workspaces/{ws_id}/suppliers/{sup_id}",
        json={"status": "FLAGGED"},
    )
    assert no_csrf_patch.status_code == 403
    assert no_csrf_patch.json()["error"]["code"] == "CSRF_TOKEN_INVALID"

    # UPLOADER & VIEWER can read suppliers but get 403 on write attempts
    for ro_client in (uploader_client, viewer_client):
        assert ro_client.get(f"/api/v1/workspaces/{ws_id}/suppliers").status_code == 200
        assert (
            ro_client.get(
                f"/api/v1/workspaces/{ws_id}/suppliers/{rev_sup_id}"
            ).status_code
            == 200
        )

        post_denied = ro_client.post(
            f"/api/v1/workspaces/{ws_id}/suppliers",
            headers=_csrf_headers(ro_client),
            json={"name": "Should Fail"},
        )
        assert post_denied.status_code == 403
        assert post_denied.json()["error"]["code"] == "FORBIDDEN_ROLE"

        patch_denied = ro_client.patch(
            f"/api/v1/workspaces/{ws_id}/suppliers/{rev_sup_id}",
            headers=_csrf_headers(ro_client),
            json={"status": "VERIFIED"},
        )
        assert patch_denied.status_code == 403
        assert patch_denied.json()["error"]["code"] == "FORBIDDEN_ROLE"


def test_supplier_invoice_aggregates_exclude_soft_deleted_and_avoid_n_plus_1(
    make_client: Callable[..., TestClient],
    db_session: Session,
) -> None:
    admin_client = make_client()
    uid = uuid.uuid4().hex[:8]
    reg = _register_user(admin_client, prefix="sup_agg", org_name=f"Agg Firm {uid}")
    ws_uuid = uuid.UUID(reg["workspace"]["workspaceId"])
    ws_id = str(ws_uuid)

    # Create 6 suppliers (1 with active + soft-deleted invoices, 5 with zero invoices)
    supplier_ids: list[str] = []
    for idx in range(6):
        resp = admin_client.post(
            f"/api/v1/workspaces/{ws_id}/suppliers",
            headers=_csrf_headers(admin_client),
            json={"name": f"Aggregate Vendor {idx:02d}"},
        )
        assert resp.status_code == 201
        supplier_ids.append(resp.json()["id"])

    target_sup_uuid = uuid.UUID(supplier_ids[0])
    other_sup_uuid = uuid.UUID(supplier_ids[1])

    # Active invoices for target supplier: 2 invoices totaling 147500.50, latest date 2026-11-12
    inv_1 = Invoice(
        workspace_id=ws_uuid,
        supplier_id=target_sup_uuid,
        supplier_name_snapshot="Aggregate Vendor 00",
        buyer_name_snapshot="Agg Firm",
        invoice_number="INV-001",
        normalized_invoice_number="inv-001",
        invoice_date=date(2026, 10, 20),
        upload_date=date(2026, 10, 21),
        total_amount=Decimal("100000.00"),
        status="PENDING_REVIEW",
    )
    inv_2 = Invoice(
        workspace_id=ws_uuid,
        supplier_id=target_sup_uuid,
        supplier_name_snapshot="Aggregate Vendor 00",
        buyer_name_snapshot="Agg Firm",
        invoice_number="INV-002",
        normalized_invoice_number="inv-002",
        invoice_date=date(2026, 11, 12),
        upload_date=date(2026, 11, 12),
        total_amount=Decimal("47500.50"),
        status="FLAGGED",
    )
    # Soft-deleted invoice with higher total & newer date -> MUST be excluded from aggregates
    inv_deleted = Invoice(
        workspace_id=ws_uuid,
        supplier_id=target_sup_uuid,
        supplier_name_snapshot="Aggregate Vendor 00",
        buyer_name_snapshot="Agg Firm",
        invoice_number="INV-DEL-003",
        normalized_invoice_number="inv-del-003",
        invoice_date=date(2026, 11, 30),
        upload_date=date(2026, 11, 30),
        total_amount=Decimal("999999.99"),
        status="PENDING_REVIEW",
        deleted_at=utc_now(),
        deletion_reason="Duplicate test draft",
    )
    # Soft-deleted-only invoice on other_sup_uuid -> totals must remain 0 / "0.00" / None
    inv_other_deleted = Invoice(
        workspace_id=ws_uuid,
        supplier_id=other_sup_uuid,
        supplier_name_snapshot="Aggregate Vendor 01",
        buyer_name_snapshot="Agg Firm",
        invoice_number="INV-DEL-004",
        normalized_invoice_number="inv-del-004",
        invoice_date=date(2026, 11, 25),
        upload_date=date(2026, 11, 25),
        total_amount=Decimal("5000.00"),
        status="FLAGGED",
        deleted_at=utc_now(),
    )
    db_session.add_all([inv_1, inv_2, inv_deleted, inv_other_deleted])
    db_session.commit()

    # Count SQL statements executed during GET /suppliers list to guarantee zero N+1 queries
    app_engine: Engine = admin_client.app.state.engine  # type: ignore[attr-defined]
    executed_statements: list[str] = []

    def _before_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ) -> None:
        executed_statements.append(statement)

    event.listen(app_engine, "before_cursor_execute", _before_cursor_execute)
    try:
        list_resp = admin_client.get(f"/api/v1/workspaces/{ws_id}/suppliers")
    finally:
        event.remove(app_engine, "before_cursor_execute", _before_cursor_execute)

    assert list_resp.status_code == 200, list_resp.text
    items = list_resp.json()["items"]
    assert len(items) == 6
    # Auth validation + membership check + count query + single aggregated suppliers query <= 6
    supplier_queries = [s for s in executed_statements if "FROM suppliers" in s]
    assert len(supplier_queries) == 2  # 1 COUNT(suppliers.id) + 1 outer-joined list query

    by_id = {item["id"]: item for item in items}
    target_item = by_id[str(target_sup_uuid)]
    assert target_item["totalInvoices"] == 2
    assert target_item["totalValue"] == "147500.50"
    assert target_item["lastInvoiceDate"] == "2026-11-12"

    other_item = by_id[str(other_sup_uuid)]
    assert other_item["totalInvoices"] == 0
    assert other_item["totalValue"] == "0.00"
    assert other_item["lastInvoiceDate"] is None

    # Detail endpoint matches aggregates identically
    detail_resp = admin_client.get(
        f"/api/v1/workspaces/{ws_id}/suppliers/{target_sup_uuid}"
    )
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["totalInvoices"] == 2
    assert detail["totalValue"] == "147500.50"
    assert detail["lastInvoiceDate"] == "2026-11-12"


def test_concurrent_duplicate_supplier_creation_returns_clean_201_and_409(
    make_client: Callable[..., TestClient],
    pg_settings: Settings,
    db_session: Session,
) -> None:
    admin_client = make_client()
    uid = uuid.uuid4().hex[:8]
    reg = _register_user(admin_client, prefix="sup_race", org_name=f"Race Firm {uid}")
    ws_id = reg["workspace"]["workspaceId"]
    cookies = dict(admin_client.cookies)
    csrf_token = cookies[CSRF_COOKIE_NAME]

    # Race 1: Concurrent duplicate normalized name (different spacing/case)
    barrier_name = threading.Barrier(2)

    def _create_same_name(name_variant: str) -> int:
        get_settings.cache_clear()
        thread_app = create_app(pg_settings)
        with TestClient(thread_app, base_url="http://testserver") as c:
            c.cookies.update(cookies)
            barrier_name.wait(timeout=5)
            resp = c.post(
                f"/api/v1/workspaces/{ws_id}/suppliers",
                headers={"X-CSRF-Token": csrf_token},
                json={"name": name_variant},
            )
            return resp.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        name_statuses = list(
            pool.map(
                _create_same_name,
                ["  Concurrent   Supply Co  ", "concurrent supply co"],
            )
        )

    assert sorted(name_statuses) == [201, 409]
    stored_names = list(
        db_session.scalars(
            select(Supplier).where(
                Supplier.workspace_id == uuid.UUID(ws_id),
                Supplier.normalized_name == "concurrent supply co",
            )
        )
    )
    assert len(stored_names) == 1

    # Race 2: Concurrent duplicate GSTIN with distinct supplier names
    barrier_gstin = threading.Barrier(2)

    def _create_same_gstin(idx: int) -> int:
        get_settings.cache_clear()
        thread_app = create_app(pg_settings)
        with TestClient(thread_app, base_url="http://testserver") as c:
            c.cookies.update(cookies)
            barrier_gstin.wait(timeout=5)
            resp = c.post(
                f"/api/v1/workspaces/{ws_id}/suppliers",
                headers={"X-CSRF-Token": csrf_token},
                json={
                    "name": f"Race GSTIN Entity {idx}",
                    "gstin": "27AABCR9999M1Z1",
                },
            )
            return resp.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        gstin_statuses = list(pool.map(_create_same_gstin, [1, 2]))

    assert sorted(gstin_statuses) == [201, 409]
    stored_gstin = list(
        db_session.scalars(
            select(Supplier).where(
                Supplier.workspace_id == uuid.UUID(ws_id),
                Supplier.gstin == "27AABCR9999M1Z1",
            )
        )
    )
    assert len(stored_gstin) == 1
