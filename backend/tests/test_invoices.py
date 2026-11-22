from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Generator
from contextlib import ExitStack
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.cookies import CSRF_COOKIE_NAME
from app.main import create_app
from app.models.accounting import (
    Document,
    Invoice,
    InvoiceLineItem,
)
from app.models.review import AuditEvent, InvoiceReviewFlag, ReviewAction
from app.models.tenancy import utc_now
from app.schemas.invoices import (
    InvoiceCreateRequest,
    InvoiceSummaryDto,
    InvoiceUpdateRequest,
    parse_financial_year_bounds,
)
from app.services.reconciliation_service import (
    compute_indian_financial_year,
    normalize_invoice_number,
    reconcile_invoice,
    resolve_line_item_inputs,
)
from tests.conftest import TEST_JWT_SECRET
from tests.test_migrations import (
    ALLOWED_POSTGRES_SCHEMES,
    APPROVED_TEST_HOSTS,
    REQUIRED_TEST_DATABASE_NAME,
    MigrationTestSafetyError,
)


# ---------------------------------------------------------------------------
# Offline unit tests: Decimal GST reconciliation, normalization & DTO validation
# ---------------------------------------------------------------------------


def test_normalize_invoice_number_unifies_formatting_while_preserving_numeric_boundaries() -> None:
    expected = "inv2026-27-001"
    for variant in (
        "INV/2026-27/001",
        "INV-2026-27-001",
        "inv 2026-27 001",
        "INV2026-27-001",
        "  INV / 2026 - 27 / 001  ",
    ):
        assert normalize_invoice_number(variant) == expected

    assert normalize_invoice_number("INV-001") == "inv001"
    assert normalize_invoice_number("INV/001") == "inv001"
    assert normalize_invoice_number("INV001") == "inv001"
    assert normalize_invoice_number("10-1") != normalize_invoice_number("1-01")


def test_indian_financial_year_helpers() -> None:
    assert compute_indian_financial_year(None) is None
    assert compute_indian_financial_year(date(2026, 3, 31)) == "2025-26"
    assert compute_indian_financial_year(date(2026, 4, 1)) == "2026-27"
    assert compute_indian_financial_year(date(2027, 2, 15)) == "2026-27"

    assert parse_financial_year_bounds("2026-27") == (date(2026, 4, 1), date(2027, 3, 31))
    assert parse_financial_year_bounds("2026-2027") == (
        date(2026, 4, 1),
        date(2027, 3, 31),
    )

    for bad_fy in ("2026", "2026-28", "abcd-ef"):
        with pytest.raises(ValueError):
            parse_financial_year_bounds(bad_fy)


def test_reconcile_invoice_decimal_gst_modes_and_tolerance_boundaries() -> None:
    # 1. Zero-input draft -> PENDING_INPUT
    pending = reconcile_invoice(
        taxable_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        discount_mode="NONE",
        cgst_amount=Decimal("0.00"),
        sgst_amount=Decimal("0.00"),
        igst_amount=Decimal("0.00"),
        cess_amount=Decimal("0.00"),
        freight_amount=Decimal("0.00"),
        other_charges_amount=Decimal("0.00"),
        round_off_amount=Decimal("0.00"),
        total_amount=Decimal("0.00"),
    )
    assert pending.reconciliation_status == "PENDING_INPUT"
    assert pending.line_item_reconciliation_status == "NO_LINE_ITEMS"
    assert pending.variance_amount == Decimal("0.00")

    # 2. Intra-state CGST + SGST with PRE_TAX discount, cess, freight, other charges & negative round-off
    intra = reconcile_invoice(
        taxable_amount=Decimal("100000.00"),
        discount_amount=Decimal("5000.00"),
        discount_mode="PRE_TAX",
        cgst_amount=Decimal("9000.00"),
        sgst_amount=Decimal("9000.00"),
        igst_amount=Decimal("0.00"),
        cess_amount=Decimal("1200.00"),
        freight_amount=Decimal("1500.00"),
        other_charges_amount=Decimal("250.35"),
        round_off_amount=Decimal("-0.35"),
        total_amount=Decimal("120950.00"),
        supplier_gstin="27AABCA4821M1Z4",
        buyer_gstin="27AAACD1234E1Z5",
        place_of_supply_code="27",
    )
    assert intra.computed_expected_total == Decimal("120950.00")
    assert intra.variance_amount == Decimal("0.00")
    assert intra.reconciliation_status == "MATCHED"
    assert intra.discrepancies == ()

    # 3. Inter-state IGST with POST_TAX_COMMERCIAL discount & positive round-off
    inter = reconcile_invoice(
        taxable_amount=Decimal("50000.00"),
        discount_amount=Decimal("1000.00"),
        discount_mode="POST_TAX_COMMERCIAL",
        cgst_amount=Decimal("0.00"),
        sgst_amount=Decimal("0.00"),
        igst_amount=Decimal("9000.00"),
        cess_amount=Decimal("0.00"),
        freight_amount=Decimal("500.00"),
        other_charges_amount=Decimal("0.00"),
        round_off_amount=Decimal("0.40"),
        total_amount=Decimal("58500.40"),
        supplier_gstin="29AAACV9102K1Z8",
        buyer_gstin="27AAACD1234E1Z5",
        place_of_supply_code="27",
    )
    assert inter.computed_expected_total == Decimal("58500.40")
    assert inter.variance_amount == Decimal("0.00")
    assert inter.reconciliation_status == "MATCHED"
    assert inter.discrepancies == ()

    # 4. Tolerance boundaries (exact 1.00 within tolerance vs 1.01 variance detected)
    within_tol = reconcile_invoice(
        taxable_amount=Decimal("1000.00"),
        discount_amount=Decimal("0.00"),
        discount_mode="NONE",
        cgst_amount=Decimal("90.00"),
        sgst_amount=Decimal("90.00"),
        igst_amount=Decimal("0.00"),
        cess_amount=Decimal("0.00"),
        freight_amount=Decimal("0.00"),
        other_charges_amount=Decimal("0.00"),
        round_off_amount=Decimal("0.00"),
        total_amount=Decimal("1181.00"),
        rounding_tolerance=Decimal("1.00"),
    )
    assert within_tol.reconciliation_status == "WITHIN_ROUNDING_TOLERANCE"
    assert within_tol.variance_amount == Decimal("1.00")

    over_tol = reconcile_invoice(
        taxable_amount=Decimal("1000.00"),
        discount_amount=Decimal("0.00"),
        discount_mode="NONE",
        cgst_amount=Decimal("90.00"),
        sgst_amount=Decimal("90.00"),
        igst_amount=Decimal("0.00"),
        cess_amount=Decimal("0.00"),
        freight_amount=Decimal("0.00"),
        other_charges_amount=Decimal("0.00"),
        round_off_amount=Decimal("0.00"),
        total_amount=Decimal("1181.01"),
        rounding_tolerance=Decimal("1.00"),
    )
    assert over_tol.reconciliation_status == "VARIANCE_DETECTED"
    assert over_tol.variance_amount == Decimal("1.01")
    assert any(d.code == "HEADER_TOTAL_VARIANCE" for d in over_tol.discrepancies)


def test_reconcile_invoice_line_items_and_advisory_discrepancies() -> None:
    # Line items whose taxable sum differs from header taxable_amount by 250.00 -> VARIANCE_WARNING
    resolved_items = resolve_line_item_inputs(
        InvoiceCreateRequest(
            supplierName="Apex Logistics",
            invoiceNumber="INV-LI-1",
            taxableAmount=Decimal("1250.00"),
            cgstAmount=Decimal("100.00"),
            sgstAmount=Decimal("80.00"),  # asymmetric CGST/SGST
            igstAmount=Decimal("50.00"),  # mixed intra + inter
            roundOffAmount=Decimal("15.00"),  # excessive round-off
            totalAmount=Decimal("1495.00"),
            isReverseCharge=True,
            supplierGstin="INVALID-GSTIN-12",
            lineItems=[
                {
                    "description": "Cloud compute hours",
                    "hsnSac": "998315",
                    "quantity": "10",
                    "unitPrice": "100.00",
                    "cgstAmount": "90.00",
                    "sgstAmount": "90.00",
                }
            ],
        ).line_items
    )
    assert len(resolved_items) == 1
    assert resolved_items[0].taxable_value == Decimal("1000.00")
    assert resolved_items[0].line_total == Decimal("1180.00")

    res = reconcile_invoice(
        taxable_amount=Decimal("1250.00"),
        discount_amount=Decimal("0.00"),
        discount_mode="NONE",
        cgst_amount=Decimal("100.00"),
        sgst_amount=Decimal("80.00"),
        igst_amount=Decimal("50.00"),
        cess_amount=Decimal("0.00"),
        freight_amount=Decimal("0.00"),
        other_charges_amount=Decimal("0.00"),
        round_off_amount=Decimal("15.00"),
        total_amount=Decimal("1495.00"),
        line_items=resolved_items,
        supplier_gstin="INVALID-GSTIN-12",
        is_reverse_charge=True,
    )
    assert res.reconciliation_status == "MATCHED"
    assert res.line_items_taxable_sum == Decimal("1000.00")
    assert res.line_item_variance_amount == Decimal("250.00")
    assert res.line_item_reconciliation_status == "VARIANCE_WARNING"
    assert res.line_item_warning is not None
    codes = {d.code for d in res.discrepancies}
    assert {
        "LINE_ITEM_TAXABLE_VARIANCE",
        "LINE_ITEM_TAX_SUM_MISMATCH",
        "MIXED_TAX_REGIME",
        "CGST_SGST_ASYMMETRY",
        "SUPPLIER_GSTIN_FORMAT",
        "REVERSE_CHARGE_TAX_CHECK",
        "EXCESSIVE_ROUND_OFF",
    }.issubset(codes)

    # State mismatch warning (same state 27 using IGST)
    state_mismatch = reconcile_invoice(
        taxable_amount=Decimal("1000.00"),
        discount_amount=Decimal("0.00"),
        discount_mode="NONE",
        cgst_amount=Decimal("0.00"),
        sgst_amount=Decimal("0.00"),
        igst_amount=Decimal("180.00"),
        cess_amount=Decimal("0.00"),
        freight_amount=Decimal("0.00"),
        other_charges_amount=Decimal("0.00"),
        round_off_amount=Decimal("0.00"),
        total_amount=Decimal("1180.00"),
        supplier_gstin="27AABCA4821M1Z4",
        place_of_supply_code="27",
    )
    assert any(d.code == "REGIME_STATE_MISMATCH" for d in state_mismatch.discrepancies)


def test_invoice_schemas_reject_status_tampering_invalid_amounts_and_serialize_fixed_decimals() -> None:
    # extra="forbid" blocks status, verified*, computed*, workspaceId injection
    for forbidden_payload in (
        {"supplierName": "Vendor", "invoiceNumber": "INV-1", "status": "VERIFIED"},
        {
            "supplierName": "Vendor",
            "invoiceNumber": "INV-1",
            "verifiedByUserId": str(uuid.uuid4()),
        },
        {"supplierName": "Vendor", "invoiceNumber": "INV-1", "workspaceId": str(uuid.uuid4())},
    ):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            InvoiceCreateRequest.model_validate(forbidden_payload)

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        InvoiceUpdateRequest.model_validate({"status": "VERIFIED"})

    # Negative money / tax > 100 / bad dates / NUL / invalid currency / missing supplier
    with pytest.raises(ValidationError):
        InvoiceCreateRequest(supplierName="Vendor", invoiceNumber="INV-1", taxableAmount="-1.00")

    with pytest.raises(ValidationError):
        InvoiceCreateRequest(
            supplierName="Vendor",
            invoiceNumber="INV-1",
            lineItems=[{"description": "Item", "taxRatePercent": "105.00"}],
        )

    with pytest.raises(ValidationError, match="dueDate"):
        InvoiceCreateRequest(
            supplierName="Vendor",
            invoiceNumber="INV-1",
            invoiceDate="2026-11-15",
            dueDate="2026-11-01",
        )

    with pytest.raises(ValidationError, match="NUL"):
        InvoiceCreateRequest(supplierName="Vendor", invoiceNumber="INV-\x001")

    with pytest.raises(ValidationError, match="currency"):
        InvoiceCreateRequest(supplierName="Vendor", invoiceNumber="INV-1", currency="12A")

    with pytest.raises(ValidationError, match="supplierId"):
        InvoiceCreateRequest(invoiceNumber="INV-1")

    with pytest.raises(ValidationError, match="At least one field"):
        InvoiceUpdateRequest()

    with pytest.raises(ValidationError, match="cannot be null"):
        InvoiceUpdateRequest.model_validate({"taxableAmount": None})

    # Fixed decimal string serialization check
    now = utc_now()
    dto = InvoiceSummaryDto(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        supplier_id=None,
        document_id=None,
        supplier_name="Acme",
        supplier_gstin="PENDING-ENTRY",
        buyer_name="Buyer",
        buyer_gstin=None,
        place_of_supply_code="27",
        place_of_supply_name=None,
        invoice_number="INV-1",
        normalized_invoice_number="inv1",
        invoice_date=date(2026, 11, 15),
        due_date=None,
        upload_date=date(2026, 11, 15),
        financial_year="2026-27",
        currency="INR",
        is_reverse_charge=False,
        tax_type="INTRA_STATE",
        taxable_amount=Decimal("100.5"),
        discount_amount=Decimal("0"),
        discount_mode="NONE",
        cgst_amount=Decimal("9.05"),
        sgst_amount=Decimal("9.05"),
        igst_amount=Decimal("0"),
        cess_amount=Decimal("0"),
        tax_amount=Decimal("18.1"),
        freight_amount=Decimal("0"),
        other_charges_amount=Decimal("0"),
        round_off_amount=Decimal("0"),
        total_amount=Decimal("118.6"),
        computed_expected_total=Decimal("118.6"),
        variance_amount=Decimal("0"),
        reconciliation_status="MATCHED",
        line_items_taxable_sum=None,
        line_item_variance_amount=None,
        line_item_reconciliation_status="NO_LINE_ITEMS",
        line_item_warning=None,
        status="PENDING_REVIEW",
        duplicate_warning=None,
        reviewer_note="",
        source_type="MANUAL_ENTRY",
        verified_by_user_id=None,
        verified_at=None,
        line_item_count=0,
        open_flag_count=0,
        created_at=now,
        updated_at=now,
    )
    dumped = dto.model_dump(by_alias=True)
    assert dumped["taxableAmount"] == "100.50"
    assert dumped["taxAmount"] == "18.10"
    assert dumped["totalAmount"] == "118.60"
    assert dumped["financialYear"] == "2026-27"


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
            "TEST_DATABASE_URL is not set; skipping PostgreSQL invoices integration tests."
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
def pg_settings(pg_test_url: str, tmp_path: Path) -> Settings:
    storage_root = tmp_path / "invoice_docs"
    storage_root.mkdir(parents=True, exist_ok=True)
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
        document_storage_root=str(storage_root),
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


def _pdf_bytes(size: int = 512) -> bytes:
    header = b"%PDF-1.7\n%invoice-test\n"
    return header + (b"0" * max(0, size - len(header)))


# ---------------------------------------------------------------------------
# PostgreSQL 16 Invoice CRUD, GST Reconciliation & Search/Filter/Sort tests
# ---------------------------------------------------------------------------


def test_invoice_crud_gst_reconciliation_search_filter_sort_and_no_n_plus_1(
    make_client: Callable[..., TestClient],
    db_session: Session,
) -> None:
    admin_client = make_client()
    uid = uuid.uuid4().hex[:8]
    reg = _register_user(admin_client, prefix="inv_crud", org_name=f"Inv Firm {uid}")
    ws_id = reg["workspace"]["workspaceId"]
    ws_uuid = uuid.UUID(ws_id)

    # Configure workspace legal buyer GSTIN
    ws_patch = admin_client.patch(
        f"/api/v1/workspaces/{ws_id}/settings",
        headers=_csrf_headers(admin_client),
        json={
            "legalEntityName": "Deshmukh Client Industries Pvt Ltd",
            "companyGstin": "27AAACD1234E1Z5",
        },
    )
    assert ws_patch.status_code == 200, ws_patch.text

    # Create suppliers & upload a document without auto-draft so we can link cleanly
    sup_mh_resp = admin_client.post(
        f"/api/v1/workspaces/{ws_id}/suppliers",
        headers=_csrf_headers(admin_client),
        json={
            "name": "Apex Industrial_50% Components",
            "gstin": "27AABCA4821M1Z4",
            "stateCode": "27",
            "stateName": "Maharashtra",
        },
    )
    assert sup_mh_resp.status_code == 201
    sup_mh_id = sup_mh_resp.json()["id"]

    sup_ka_resp = admin_client.post(
        f"/api/v1/workspaces/{ws_id}/suppliers",
        headers=_csrf_headers(admin_client),
        json={
            "name": "Vindhya Cloud Services",
            "gstin": "29AAACV9102K1Z8",
            "stateCode": "29",
            "stateName": "Karnataka",
        },
    )
    assert sup_ka_resp.status_code == 201
    sup_ka_id = sup_ka_resp.json()["id"]

    doc_resp = admin_client.post(
        f"/api/v1/workspaces/{ws_id}/documents",
        headers=_csrf_headers(admin_client),
        files={"file": ("apex_bill.pdf", _pdf_bytes(1024), "application/pdf")},
        data={"createDraftInvoice": "false"},
    )
    assert doc_resp.status_code == 201
    doc_id = doc_resp.json()["document"]["id"]

    # 1. Create document-linked intra-state invoice with PRE_TAX discount, cess, freight & round-off
    create_1 = admin_client.post(
        f"/api/v1/workspaces/{ws_id}/invoices",
        headers=_csrf_headers(admin_client),
        json={
            "supplierId": sup_mh_id,
            "documentId": doc_id,
            "invoiceNumber": "INV/2026-27/001",
            "invoiceDate": "2026-10-15",
            "dueDate": "2026-11-15",
            "discountAmount": "2000.00",
            "discountMode": "PRE_TAX",
            "taxableAmount": "100000.00",
            "cgstAmount": "9000.00",
            "sgstAmount": "9000.00",
            "cessAmount": "500.00",
            "freightAmount": "1000.00",
            "otherChargesAmount": "250.45",
            "roundOffAmount": "-0.45",
            "totalAmount": "119750.00",
            "lineItems": [
                {
                    "description": "Industrial Bearings",
                    "hsnSac": "8482",
                    "quantity": "10",
                    "unitPrice": "10200.00",
                    "discountAmount": "2000.00",
                    "taxRatePercent": "18.00",
                    "cgstAmount": "9000.00",
                    "sgstAmount": "9000.00",
                    "cessAmount": "500.00",
                }
            ],
        },
    )
    assert create_1.status_code == 201, create_1.text
    inv1 = create_1.json()
    assert inv1["status"] == "PENDING_REVIEW"
    assert inv1["verifiedByUserId"] is None
    assert inv1["verifiedAt"] is None
    assert inv1["sourceType"] == "MANUAL_UPLOAD"
    assert inv1["supplierName"] == "Apex Industrial_50% Components"
    assert inv1["supplierGstin"] == "27AABCA4821M1Z4"
    assert inv1["buyerName"] == "Deshmukh Client Industries Pvt Ltd"
    assert inv1["buyerGstin"] == "27AAACD1234E1Z5"
    assert inv1["placeOfSupplyCode"] == "27"
    assert inv1["financialYear"] == "2026-27"
    assert inv1["taxType"] == "INTRA_STATE"
    assert inv1["taxAmount"] == "18500.00"
    assert inv1["computedExpectedTotal"] == "119750.00"
    assert inv1["varianceAmount"] == "0.00"
    assert inv1["reconciliationStatus"] == "MATCHED"
    assert inv1["lineItemsTaxableSum"] == "100000.00"
    assert inv1["lineItemVarianceAmount"] == "0.00"
    assert inv1["lineItemReconciliationStatus"] == "MATCHED"
    assert inv1["lineItemWarning"] is None
    assert inv1["document"]["id"] == doc_id
    assert "storageKey" not in str(inv1["document"])
    assert len(inv1["lineItems"]) == 1
    assert inv1["lineItems"][0]["taxableValue"] == "100000.00"
    assert inv1["lineItems"][0]["lineTotal"] == "118500.00"

    # 2. Create manual inter-state invoice WITH deliberate header + line-item variance
    # Must NOT reject or overwrite values (non-blocking advisory warning only)
    create_2 = admin_client.post(
        f"/api/v1/workspaces/{ws_id}/invoices",
        headers=_csrf_headers(admin_client),
        json={
            "supplierId": sup_ka_id,
            "invoiceNumber": "VCS-2526-099",
            "invoiceDate": "2026-02-20",  # FY 2025-26
            "discountAmount": "500.00",
            "discountMode": "POST_TAX_COMMERCIAL",
            "taxableAmount": "50000.00",
            "igstAmount": "9000.00",
            "totalAmount": "59500.00",  # expected = 50000 - 500 + 9000 = 58500 -> +1000.00 variance
            "lineItems": [
                {
                    "description": "SaaS Subscription",
                    "hsnSac": "998314",
                    "quantity": "1",
                    "unitPrice": "48000.00",
                    "taxableValue": "48000.00",
                }
            ],
        },
    )
    assert create_2.status_code == 201, create_2.text
    inv2 = create_2.json()
    assert inv2["sourceType"] == "MANUAL_ENTRY"
    assert inv2["financialYear"] == "2025-26"
    assert inv2["taxType"] == "INTER_STATE"
    assert inv2["totalAmount"] == "59500.00"
    assert inv2["computedExpectedTotal"] == "58500.00"
    assert inv2["varianceAmount"] == "1000.00"
    assert inv2["reconciliationStatus"] == "VARIANCE_DETECTED"
    assert inv2["lineItemsTaxableSum"] == "48000.00"
    assert inv2["lineItemVarianceAmount"] == "2000.00"
    assert inv2["lineItemReconciliationStatus"] == "VARIANCE_WARNING"
    assert inv2["lineItemWarning"] is not None
    assert {d["code"] for d in inv2["reconciliation"]["discrepancies"]} >= {
        "HEADER_TOTAL_VARIANCE",
        "LINE_ITEM_TAXABLE_VARIANCE",
    }

    # 3. Create unregistered supplier invoice within rounding tolerance (0.60)
    create_3 = admin_client.post(
        f"/api/v1/workspaces/{ws_id}/invoices",
        headers=_csrf_headers(admin_client),
        json={
            "supplierName": "Local Stationery Mart",
            "supplierGstin": "URD",
            "invoiceNumber": "LSM-77",
            "invoiceDate": "2026-11-10",
            "taxableAmount": "1000.00",
            "cgstAmount": "90.00",
            "sgstAmount": "90.00",
            "totalAmount": "1180.60",
        },
    )
    assert create_3.status_code == 201, create_3.text
    inv3 = create_3.json()
    assert inv3["reconciliationStatus"] == "WITHIN_ROUNDING_TOLERANCE"
    assert inv3["varianceAmount"] == "0.60"
    assert inv3["lineItemReconciliationStatus"] == "NO_LINE_ITEMS"

    # 4. PATCH inv2: resolve line-item sum and add fieldVerifications
    patch_inv2 = admin_client.patch(
        f"/api/v1/workspaces/{ws_id}/invoices/{inv2['id']}",
        headers=_csrf_headers(admin_client),
        json={
            "totalAmount": "58500.00",
            "reviewerNote": "Confirmed commercial discount applied post tax.",
            "lineItems": [
                {
                    "description": "SaaS Subscription",
                    "hsnSac": "998314",
                    "quantity": "1",
                    "unitPrice": "48000.00",
                    "taxableValue": "48000.00",
                },
                {
                    "description": "Onboarding Setup",
                    "hsnSac": "998314",
                    "quantity": "1",
                    "unitPrice": "2000.00",
                },
            ],
            "fieldVerifications": [
                {
                    "fieldKey": "totalAmount",
                    "status": "VERIFIED",
                    "evidenceNote": "Matched PDF page 1 footer",
                    "sourcePage": 1,
                }
            ],
        },
    )
    assert patch_inv2.status_code == 200, patch_inv2.text
    patched2 = patch_inv2.json()
    assert patched2["reconciliationStatus"] == "MATCHED"
    assert patched2["lineItemReconciliationStatus"] == "MATCHED"
    assert patched2["lineItemWarning"] is None
    assert len(patched2["lineItems"]) == 2
    assert len(patched2["fieldVerifications"]) == 1
    assert patched2["fieldVerifications"][0]["status"] == "VERIFIED"

    # 5. List search (literal _50% LIKE escaping + normalized number search), filters, sorting & N+1 bound
    app_engine: Engine = admin_client.app.state.engine  # type: ignore[attr-defined]
    executed_statements: list[str] = []

    def _before_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ) -> None:
        executed_statements.append(statement)

    event.listen(app_engine, "before_cursor_execute", _before_cursor_execute)
    try:
        list_resp = admin_client.get(
            f"/api/v1/workspaces/{ws_id}/invoices",
            params={"sortBy": "totalAmount", "sortDir": "desc", "page": 1, "pageSize": 2},
        )
    finally:
        event.remove(app_engine, "before_cursor_execute", _before_cursor_execute)

    assert list_resp.status_code == 200, list_resp.text
    list_json = list_resp.json()
    assert list_json["total"] == 3
    assert [i["id"] for i in list_json["items"]] == [inv1["id"], inv2["id"]]
    assert list_json["items"][0]["lineItemCount"] == 1
    invoice_queries = [s for s in executed_statements if "FROM invoices" in s]
    assert len(invoice_queries) == 2  # COUNT + single joined list query

    # Search with literal _50%
    pct_resp = admin_client.get(
        f"/api/v1/workspaces/{ws_id}/invoices",
        params={"search": "_50%"},
    )
    assert pct_resp.status_code == 200
    assert [i["id"] for i in pct_resp.json()["items"]] == [inv1["id"]]

    # Search with normalized formatting variation of invoice number
    norm_search_resp = admin_client.get(
        f"/api/v1/workspaces/{ws_id}/invoices",
        params={"search": "inv-2026-27-001"},
    )
    assert norm_search_resp.status_code == 200
    assert [i["id"] for i in norm_search_resp.json()["items"]] == [inv1["id"]]

    # Filter combinations
    assert (
        admin_client.get(
            f"/api/v1/workspaces/{ws_id}/invoices",
            params={"taxType": "INTER_STATE"},
        ).json()["total"]
        == 1
    )
    assert (
        admin_client.get(
            f"/api/v1/workspaces/{ws_id}/invoices",
            params={"financialYear": "2025-26"},
        ).json()["items"][0]["id"]
        == inv2["id"]
    )
    assert (
        admin_client.get(
            f"/api/v1/workspaces/{ws_id}/invoices",
            params={"documentId": doc_id},
        ).json()["items"][0]["id"]
        == inv1["id"]
    )
    assert (
        admin_client.get(
            f"/api/v1/workspaces/{ws_id}/invoices",
            params={"reconciliationStatus": "WITHIN_ROUNDING_TOLERANCE"},
        ).json()["items"][0]["id"]
        == inv3["id"]
    )
    assert (
        admin_client.get(
            f"/api/v1/workspaces/{ws_id}/invoices",
            params={"dateFrom": "2026-11-01", "dateTo": "2026-10-01"},
        ).status_code
        == 422
    )

    # Audit events check
    events = list(
        db_session.scalars(
            select(AuditEvent).where(
                AuditEvent.workspace_id == ws_uuid,
                AuditEvent.entity_type == "invoice",
            )
        )
    )
    assert [e.event_type for e in events].count("invoice.created") == 3
    assert [e.event_type for e in events].count("invoice.updated") == 1


def test_invoice_advisory_duplicate_detection_respects_fy_window_soft_delete_and_settings(
    make_client: Callable[..., TestClient],
) -> None:
    admin_client = make_client()
    uid = uuid.uuid4().hex[:8]
    reg = _register_user(admin_client, prefix="inv_dup", org_name=f"Dup Firm {uid}")
    ws_id = reg["workspace"]["workspaceId"]

    sup_resp = admin_client.post(
        f"/api/v1/workspaces/{ws_id}/suppliers",
        headers=_csrf_headers(admin_client),
        json={"name": "Kaveri Paper Solutions", "gstin": "33AAACK8812R1Z9"},
    )
    assert sup_resp.status_code == 201
    sup_id = sup_resp.json()["id"]

    # Base invoice in FY 2026-27
    base_resp = admin_client.post(
        f"/api/v1/workspaces/{ws_id}/invoices",
        headers=_csrf_headers(admin_client),
        json={
            "supplierId": sup_id,
            "invoiceNumber": "INV/2026-27/001",
            "invoiceDate": "2026-10-01",
            "taxableAmount": "10000.00",
            "igstAmount": "1800.00",
            "totalAmount": "11800.00",
        },
    )
    assert base_resp.status_code == 201
    base_id = base_resp.json()["id"]
    assert base_resp.json()["duplicateWarning"] is None

    # 1. Normalized number formatting variant in same FY -> creates 201 WITH advisory warning
    dup_num_resp = admin_client.post(
        f"/api/v1/workspaces/{ws_id}/invoices",
        headers=_csrf_headers(admin_client),
        json={
            "supplierId": sup_id,
            "invoiceNumber": "inv-2026-27-001",
            "invoiceDate": "2026-10-05",
            "taxableAmount": "20000.00",
            "igstAmount": "3600.00",
            "totalAmount": "23600.00",
        },
    )
    assert dup_num_resp.status_code == 201, dup_num_resp.text
    dup_num_json = dup_num_resp.json()
    assert dup_num_json["duplicateWarning"] is not None
    assert any(
        m["invoiceId"] == base_id
        and "NORMALIZED_INVOICE_NUMBER" in m["matchReasons"]
        for m in dup_num_json["duplicateMatches"]
    )

    # Soft-delete dup_num so subsequent checks stay crisp
    assert (
        admin_client.delete(
            f"/api/v1/workspaces/{ws_id}/invoices/{dup_num_json['id']}",
            headers=_csrf_headers(admin_client),
        ).status_code
        == 204
    )

    # 2. Same normalized number > 1 year apart (different Indian FY) -> NO false duplicate
    cross_fy_resp = admin_client.post(
        f"/api/v1/workspaces/{ws_id}/invoices",
        headers=_csrf_headers(admin_client),
        json={
            "supplierId": sup_id,
            "invoiceNumber": "INV-2026-27-001",
            "invoiceDate": "2025-04-10",
            "taxableAmount": "5000.00",
            "igstAmount": "900.00",
            "totalAmount": "5900.00",
        },
    )
    assert cross_fy_resp.status_code == 201
    assert cross_fy_resp.json()["duplicateWarning"] is None

    # 3. Same supplier + total within +/-0.01 + date within 45 days -> advisory amount warning
    amt_dup_resp = admin_client.post(
        f"/api/v1/workspaces/{ws_id}/invoices",
        headers=_csrf_headers(admin_client),
        json={
            "supplierId": sup_id,
            "invoiceNumber": "INV/2026-27/099",
            "invoiceDate": "2026-10-20",
            "taxableAmount": "10000.00",
            "igstAmount": "1800.01",
            "totalAmount": "11800.01",
        },
    )
    assert amt_dup_resp.status_code == 201
    amt_dup_json = amt_dup_resp.json()
    assert amt_dup_json["duplicateWarning"] is not None
    assert any(
        m["invoiceId"] == base_id
        and "SIMILAR_TOTAL_WITHIN_45_DAYS" in m["matchReasons"]
        for m in amt_dup_json["duplicateMatches"]
    )

    # 4. Same total > 45 days away -> NO amount duplicate
    far_date_resp = admin_client.post(
        f"/api/v1/workspaces/{ws_id}/invoices",
        headers=_csrf_headers(admin_client),
        json={
            "supplierId": sup_id,
            "invoiceNumber": "INV/2026-27/120",
            "invoiceDate": "2026-12-20",
            "taxableAmount": "10000.00",
            "igstAmount": "1800.00",
            "totalAmount": "11800.00",
        },
    )
    assert far_date_resp.status_code == 201
    assert far_date_resp.json()["duplicateWarning"] is None

    # 5. Disabling enableDuplicateWarnings in WorkspaceSettings suppresses duplicate warnings
    disable_dup = admin_client.patch(
        f"/api/v1/workspaces/{ws_id}/settings",
        headers=_csrf_headers(admin_client),
        json={"enableDuplicateWarnings": False},
    )
    assert disable_dup.status_code == 200

    suppressed_resp = admin_client.post(
        f"/api/v1/workspaces/{ws_id}/invoices",
        headers=_csrf_headers(admin_client),
        json={
            "supplierId": sup_id,
            "invoiceNumber": "INV/2026-27/001",
            "invoiceDate": "2026-10-02",
            "taxableAmount": "10000.00",
            "igstAmount": "1800.00",
            "totalAmount": "11800.00",
        },
    )
    assert suppressed_resp.status_code == 201
    assert suppressed_resp.json()["duplicateWarning"] is None
    assert suppressed_resp.json()["duplicateMatches"] == []


def test_invoice_relationship_validation_scan_gating_rbac_verified_lock_and_soft_delete(
    make_client: Callable[..., TestClient],
    db_session: Session,
) -> None:
    admin_client = make_client()
    reviewer_client = make_client()
    uploader_client = make_client()
    viewer_client = make_client()
    foreign_client = make_client()
    uid = uuid.uuid4().hex[:8]

    reg_admin = _register_user(admin_client, prefix="inv_adm", org_name=f"RBAC Inv {uid}")
    org_id = reg_admin["organization"]["id"]
    ws1_id = reg_admin["workspace"]["workspaceId"]

    # Sibling workspace in same org for intra-org isolation tests
    ws2_resp = admin_client.post(
        f"/api/v1/organizations/{org_id}/workspaces",
        headers=_csrf_headers(admin_client),
        json={
            "name": "Sibling Workspace",
            "workspaceCode": f"SIB-{uid}".upper(),
            "legalEntityName": "Sibling Entity Pvt Ltd",
        },
    )
    assert ws2_resp.status_code == 201
    ws2_id = ws2_resp.json()["workspace"]["id"]

    reg_rev = _register_user(reviewer_client, prefix="inv_rev", full_name="Reviewer")
    reg_upl = _register_user(uploader_client, prefix="inv_upl", full_name="Uploader")
    reg_view = _register_user(viewer_client, prefix="inv_view", full_name="Viewer")
    reg_for = _register_user(foreign_client, prefix="inv_for", org_name=f"Foreign {uid}")
    ws_for_id = reg_for["workspace"]["workspaceId"]

    _onboard_to_workspace(
        admin_client,
        org_id=org_id,
        workspace_id=ws1_id,
        member_client=reviewer_client,
        member_email=reg_rev["user"]["email"],
        workspace_role="REVIEWER",
    )
    _onboard_to_workspace(
        admin_client,
        org_id=org_id,
        workspace_id=ws1_id,
        member_client=uploader_client,
        member_email=reg_upl["user"]["email"],
        workspace_role="UPLOADER",
    )
    _onboard_to_workspace(
        admin_client,
        org_id=org_id,
        workspace_id=ws1_id,
        member_client=viewer_client,
        member_email=reg_view["user"]["email"],
        workspace_role="VIEWER",
    )

    # Foreign supplier & document (in sibling workspace ws2 and foreign tenant) -> must return 404
    ws2_sup = admin_client.post(
        f"/api/v1/workspaces/{ws2_id}/suppliers",
        headers=_csrf_headers(admin_client),
        json={"name": "Sibling Supplier"},
    ).json()
    ws2_doc = admin_client.post(
        f"/api/v1/workspaces/{ws2_id}/documents",
        headers=_csrf_headers(admin_client),
        files={"file": ("sib.pdf", _pdf_bytes(), "application/pdf")},
        data={"createDraftInvoice": "false"},
    ).json()["document"]

    assert (
        admin_client.post(
            f"/api/v1/workspaces/{ws1_id}/invoices",
            headers=_csrf_headers(admin_client),
            json={"supplierId": ws2_sup["id"], "invoiceNumber": "X-1"},
        ).status_code
        == 404
    )
    assert (
        admin_client.post(
            f"/api/v1/workspaces/{ws1_id}/invoices",
            headers=_csrf_headers(admin_client),
            json={
                "supplierName": "Valid Name",
                "documentId": ws2_doc["id"],
                "invoiceNumber": "X-2",
            },
        ).status_code
        == 404
    )

    # Scan status validation on documentId linking
    ws1_doc_id = admin_client.post(
        f"/api/v1/workspaces/{ws1_id}/documents",
        headers=_csrf_headers(admin_client),
        files={"file": ("scan_gate.pdf", _pdf_bytes(), "application/pdf")},
        data={"createDraftInvoice": "false"},
    ).json()["document"]["id"]
    ws1_doc_row = db_session.get(Document, uuid.UUID(ws1_doc_id))
    assert ws1_doc_row is not None

    ws1_doc_row.scan_status = "INFECTED"
    db_session.commit()
    infected_link = admin_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices",
        headers=_csrf_headers(admin_client),
        json={
            "supplierName": "Vendor",
            "documentId": ws1_doc_id,
            "invoiceNumber": "INF-1",
        },
    )
    assert infected_link.status_code == 409
    assert infected_link.json()["error"]["code"] == "DOCUMENT_INFECTED"

    ws1_doc_row.scan_status = "FAILED"
    db_session.commit()
    failed_link = admin_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices",
        headers=_csrf_headers(admin_client),
        json={
            "supplierName": "Vendor",
            "documentId": ws1_doc_id,
            "invoiceNumber": "FAIL-1",
        },
    )
    assert failed_link.status_code == 409
    assert failed_link.json()["error"]["code"] == "DOCUMENT_SCAN_FAILED"

    # PENDING document links cleanly while content download stays 409
    ws1_doc_row.scan_status = "PENDING"
    db_session.commit()

    # CSRF check
    assert (
        uploader_client.post(
            f"/api/v1/workspaces/{ws1_id}/invoices",
            json={"supplierName": "No CSRF", "invoiceNumber": "CSRF-1"},
        ).status_code
        == 403
    )

    # UPLOADER creates PENDING_REVIEW invoice and updates it while PENDING_REVIEW
    upl_create = uploader_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices",
        headers=_csrf_headers(uploader_client),
        json={
            "supplierName": "Draft Vendor",
            "documentId": ws1_doc_id,
            "invoiceNumber": "UPL-001",
            "taxableAmount": "1000.00",
            "totalAmount": "1000.00",
        },
    )
    assert upl_create.status_code == 201, upl_create.text
    inv_id = upl_create.json()["id"]

    assert (
        uploader_client.patch(
            f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}",
            headers=_csrf_headers(uploader_client),
            json={"reviewerNote": "Updated by uploader"},
        ).status_code
        == 200
    )

    # UPLOADER cannot mark fieldVerifications as VERIFIED
    assert (
        uploader_client.patch(
            f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}",
            headers=_csrf_headers(uploader_client),
            json={
                "fieldVerifications": [
                    {"fieldKey": "totalAmount", "status": "VERIFIED"}
                ]
            },
        ).status_code
        == 403
    )

    # VIEWER cannot create, update, or delete
    assert (
        viewer_client.get(f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}").status_code
        == 200
    )
    assert (
        viewer_client.post(
            f"/api/v1/workspaces/{ws1_id}/invoices",
            headers=_csrf_headers(viewer_client),
            json={"supplierName": "Blocked", "invoiceNumber": "VW-1"},
        ).status_code
        == 403
    )
    assert (
        viewer_client.patch(
            f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}",
            headers=_csrf_headers(viewer_client),
            json={"reviewerNote": "Blocked"},
        ).status_code
        == 403
    )
    assert (
        viewer_client.delete(
            f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}",
            headers=_csrf_headers(viewer_client),
        ).status_code
        == 403
    )

    # REVIEWER cannot delete (WORKSPACE_ADMIN only)
    assert (
        reviewer_client.delete(
            f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}",
            headers=_csrf_headers(reviewer_client),
        ).status_code
        == 403
    )

    # Cross-workspace 404 isolation
    assert (
        admin_client.get(
            f"/api/v1/workspaces/{ws2_id}/invoices/{inv_id}"
        ).status_code
        == 404
    )
    assert (
        foreign_client.get(
            f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}"
        ).status_code
        == 404
    )
    assert (
        foreign_client.delete(
            f"/api/v1/workspaces/{ws_for_id}/invoices/{inv_id}",
            headers=_csrf_headers(foreign_client),
        ).status_code
        == 404
    )

    # FLAGGED state blocks UPLOADER PATCH (403) while allowing REVIEWER PATCH (200)
    db_inv = db_session.get(Invoice, uuid.UUID(inv_id))
    assert db_inv is not None
    db_inv.status = "FLAGGED"
    db_session.commit()

    assert (
        uploader_client.patch(
            f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}",
            headers=_csrf_headers(uploader_client),
            json={"reviewerNote": "Uploader blocked on FLAGGED"},
        ).status_code
        == 403
    )
    assert (
        reviewer_client.patch(
            f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}",
            headers=_csrf_headers(reviewer_client),
            json={"reviewerNote": "Reviewer allowed on FLAGGED"},
        ).status_code
        == 200
    )

    # VERIFIED invoice blocks PATCH (409 VERIFIED_INVOICE_LOCKED) & DELETE (409 CANNOT_DELETE_VERIFIED_INVOICE)
    db_inv.status = "VERIFIED"
    db_inv.verified_by_user_id = uuid.UUID(reg_admin["user"]["id"])
    db_inv.verified_at = utc_now()
    db_session.commit()

    locked_patch = reviewer_client.patch(
        f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}",
        headers=_csrf_headers(reviewer_client),
        json={"reviewerNote": "Should fail"},
    )
    assert locked_patch.status_code == 409
    assert locked_patch.json()["error"]["code"] == "VERIFIED_INVOICE_LOCKED"

    locked_delete = admin_client.delete(
        f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}",
        headers=_csrf_headers(admin_client),
    )
    assert locked_delete.status_code == 409
    assert locked_delete.json()["error"]["code"] == "CANNOT_DELETE_VERIFIED_INVOICE"

    # Soft-delete unverified FLAGGED invoice with attached review flag + action + audit history
    flagged_create = admin_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices",
        headers=_csrf_headers(admin_client),
        json={
            "supplierName": "Delete Test Vendor",
            "invoiceNumber": "DEL-001",
            "lineItems": [{"description": "Test line", "unitPrice": "100.00"}],
            "taxableAmount": "100.00",
            "totalAmount": "100.00",
        },
    ).json()
    del_id = uuid.UUID(flagged_create["id"])
    del_row = db_session.get(Invoice, del_id)
    assert del_row is not None
    del_row.status = "FLAGGED"
    db_session.add(
        InvoiceReviewFlag(
            workspace_id=uuid.UUID(ws1_id),
            invoice_id=del_id,
            flag_category="CUSTOM",
            reason_text="Test flag preserved after soft delete",
            status="OPEN",
            created_by_user_id=uuid.UUID(reg_admin["user"]["id"]),
        )
    )
    db_session.add(
        ReviewAction(
            workspace_id=uuid.UUID(ws1_id),
            invoice_id=del_id,
            actor_user_id=uuid.UUID(reg_admin["user"]["id"]),
            action_type="FLAG_INVOICE",
            previous_status="PENDING_REVIEW",
            new_status="FLAGGED",
            comment="Preserved review decision",
        )
    )
    db_session.commit()

    del_resp = admin_client.request(
        "DELETE",
        f"/api/v1/workspaces/{ws1_id}/invoices/{del_id}",
        headers=_csrf_headers(admin_client),
        json={"deletionReason": "Duplicate test scan uploaded by mistake"},
    )
    assert del_resp.status_code == 204

    # Excluded from GET detail & list afterwards
    assert (
        admin_client.get(f"/api/v1/workspaces/{ws1_id}/invoices/{del_id}").status_code
        == 404
    )
    listed_ids = {
        item["id"]
        for item in admin_client.get(f"/api/v1/workspaces/{ws1_id}/invoices").json()[
            "items"
        ]
    }
    assert str(del_id) not in listed_ids

    # DB row + child flags + review actions + audit events remain preserved
    db_session.expire_all()
    preserved_inv = db_session.get(Invoice, del_id)
    assert preserved_inv is not None
    assert preserved_inv.deleted_at is not None
    assert preserved_inv.deletion_reason == "Duplicate test scan uploaded by mistake"
    assert (
        len(
            list(
                db_session.scalars(
                    select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == del_id)
                )
            )
        )
        == 1
    )
    assert (
        len(
            list(
                db_session.scalars(
                    select(InvoiceReviewFlag).where(
                        InvoiceReviewFlag.invoice_id == del_id
                    )
                )
            )
        )
        == 1
    )
    assert (
        len(
            list(
                db_session.scalars(
                    select(ReviewAction).where(ReviewAction.invoice_id == del_id)
                )
            )
        )
        == 1
    )
    assert any(
        e.event_type == "invoice.soft_deleted"
        for e in db_session.scalars(
            select(AuditEvent).where(AuditEvent.entity_id == del_id)
        )
    )


def test_postgres_invoice_constraints_block_unverified_delete_and_unattributed_verify(
    make_client: Callable[..., TestClient],
    db_session: Session,
) -> None:
    admin_client = make_client()
    uid = uuid.uuid4().hex[:8]
    reg = _register_user(admin_client, prefix="inv_chk", org_name=f"Chk Firm {uid}")
    ws_uuid = uuid.UUID(reg["workspace"]["workspaceId"])
    user_uuid = uuid.UUID(reg["user"]["id"])

    # Verified without human verifier -> ck_invoices_invoice_verified_requires_human_actor
    bad_verified = Invoice(
        workspace_id=ws_uuid,
        supplier_name_snapshot="Vendor",
        buyer_name_snapshot="Buyer",
        invoice_number="CHK-1",
        normalized_invoice_number="chk1",
        upload_date=date.today(),
        status="VERIFIED",
        verified_by_user_id=None,
        verified_at=None,
    )
    db_session.add(bad_verified)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Soft-deleting a VERIFIED invoice directly in DB -> ck_invoices_invoice_soft_delete_unverified_only
    bad_deleted_verified = Invoice(
        workspace_id=ws_uuid,
        supplier_name_snapshot="Vendor",
        buyer_name_snapshot="Buyer",
        invoice_number="CHK-2",
        normalized_invoice_number="chk2",
        upload_date=date.today(),
        status="VERIFIED",
        verified_by_user_id=user_uuid,
        verified_at=utc_now(),
        deleted_at=utc_now(),
    )
    db_session.add(bad_deleted_verified)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
