from __future__ import annotations

import ast
import os
import sys
import uuid
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

import app.models  # noqa: F401 - register all ORM models on Base.metadata
from app.db.base import Base

EXPECTED_TABLES = {
    "organizations",
    "users",
    "user_sessions",
    "workspaces",
    "workspace_settings",
    "organization_memberships",
    "organization_invitations",
    "workspace_memberships",
    "auth_rate_limit_buckets",
    "suppliers",
    "documents",
    "invoices",
    "invoice_line_items",
    "invoice_field_verifications",
    "invoice_review_flags",
    "review_actions",
    "audit_events",
}

ALLOWED_POSTGRES_SCHEMES = {"postgresql", "postgresql+psycopg"}
REQUIRED_TEST_DATABASE_NAME = "norus_billwise_test"
APPROVED_TEST_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres"}


class MigrationTestSafetyError(ValueError):
    """Raised when migration tests receive an unsafe, malformed, or unapproved DB target."""


def validate_destructive_migration_target(
    test_db_url: str | None,
    *,
    allow_destructive: bool,
    require_postgres_tests: bool = False,
) -> str | None:
    """Validate that destructive Alembic downgrade tests target ONLY an isolated local/CI test DB.

    Returns the validated URL if safe to proceed, or ``None`` if optional local
    migration tests should be skipped. Raises ``MigrationTestSafetyError`` before
    opening any DB connection or invoking Alembic whenever a configured target is
    malformed, unapproved, missing destructive opt-in, or missing while required.
    Never exposes credentials or full URLs in error messages.
    """
    raw_url = (test_db_url or "").strip()
    if not raw_url:
        if require_postgres_tests:
            raise MigrationTestSafetyError(
                "TEST_DATABASE_URL is required when NORUS_REQUIRE_POSTGRES_TESTS=1."
            )
        return None

    try:
        parsed = urlparse(raw_url)
        port = parsed.port
    except ValueError as exc:
        raise MigrationTestSafetyError(
            "TEST_DATABASE_URL is malformed (invalid port or URL syntax)."
        ) from exc

    if port is not None and not (1 <= port <= 65535):
        raise MigrationTestSafetyError("TEST_DATABASE_URL specifies an out-of-range port.")

    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_POSTGRES_SCHEMES:
        raise MigrationTestSafetyError(
            "TEST_DATABASE_URL must use postgresql:// or postgresql+psycopg://."
        )

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise MigrationTestSafetyError(
            "TEST_DATABASE_URL is malformed (missing database hostname)."
        )

    if hostname not in APPROVED_TEST_HOSTS:
        raise MigrationTestSafetyError(
            f"Refusing destructive migration test on unapproved host {hostname!r}; "
            "only localhost, 127.0.0.1, ::1, and 'postgres' are permitted."
        )

    db_name = parsed.path.lstrip("/")
    if not db_name or "/" in db_name:
        raise MigrationTestSafetyError(
            "TEST_DATABASE_URL is malformed (invalid database path)."
        )

    if db_name != REQUIRED_TEST_DATABASE_NAME:
        raise MigrationTestSafetyError(
            f"Refusing destructive migration test on database {db_name!r}; "
            f"exact database name {REQUIRED_TEST_DATABASE_NAME!r} is required."
        )

    if not allow_destructive:
        raise MigrationTestSafetyError(
            "NORUS_ALLOW_DESTRUCTIVE_MIGRATION_TEST=1 is required before running "
            "destructive Alembic downgrade tests."
        )

    return raw_url


def _resolve_validated_postgres_test_url() -> str:
    """Resolve and validate TEST_DATABASE_URL or cleanly skip/fail per env flags."""
    require_pg = os.environ.get("NORUS_REQUIRE_POSTGRES_TESTS", "").strip() == "1"
    allow_destructive = (
        os.environ.get("NORUS_ALLOW_DESTRUCTIVE_MIGRATION_TEST", "").strip() == "1"
    )
    raw_url = os.environ.get("TEST_DATABASE_URL", "")

    try:
        validated = validate_destructive_migration_target(
            raw_url,
            allow_destructive=allow_destructive,
            require_postgres_tests=require_pg,
        )
    except MigrationTestSafetyError as exc:
        pytest.fail(str(exc), pytrace=False)

    if validated is None:
        pytest.skip(
            "TEST_DATABASE_URL is not set; skipping PostgreSQL Alembic migration test."
        )
    return validated


def test_alembic_upgrade_and_downgrade_on_postgresql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_url = _resolve_validated_postgres_test_url()
    require_pg = os.environ.get("NORUS_REQUIRE_POSTGRES_TESTS", "").strip() == "1"

    engine = create_engine(db_url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        engine.dispose()
        error_type = type(exc).__name__
        if require_pg:
            pytest.fail(
                f"PostgreSQL migration test failed: database unreachable ({error_type}) "
                "while NORUS_REQUIRE_POSTGRES_TESTS=1.",
                pytrace=False,
            )
        pytest.skip(f"PostgreSQL instance unavailable for migration test ({error_type}).")

    # Regression guard: ambient DATABASE_URL must not override explicit Test config URL.
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://wrong:wrong@127.0.0.1:59999/should_not_be_used",
    )

    backend_dir = Path(__file__).resolve().parents[1]
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    try:
        # Clean slate -> upgrade -> inspect -> downgrade -> re-upgrade
        command.downgrade(alembic_cfg, "base")
        command.upgrade(alembic_cfg, "head")

        inspector = inspect(engine)
        present_tables = set(inspector.get_table_names())
        assert EXPECTED_TABLES.issubset(present_tables)

        user_indexes = {idx["name"] for idx in inspector.get_indexes("users")}
        assert "uq_users_email_lower" in user_indexes

        for table_name in EXPECTED_TABLES:
            table_checks = {
                ck["name"]
                for ck in inspector.get_check_constraints(table_name)
                if ck.get("name")
            }
            for ck_name in table_checks:
                assert not ck_name.startswith(f"ck_{table_name}_ck_"), (
                    f"Duplicate ck_ prefix detected in PostgreSQL on {table_name}: {ck_name}"
                )

            expected_table_checks = {
                constraint.name
                for constraint in Base.metadata.tables[table_name].constraints
                if isinstance(constraint, CheckConstraint) and constraint.name is not None
            }
            assert expected_table_checks.issubset(table_checks), (
                f"Missing check constraints on {table_name}: "
                f"expected {expected_table_checks}, got {table_checks}"
            )

        invoice_checks = {
            ck["name"] for ck in inspector.get_check_constraints("invoices")
        }
        assert {
            "ck_invoices_invoice_discount_mode_valid",
            "ck_invoices_invoice_reconciliation_status_valid",
            "ck_invoices_invoice_line_item_reconciliation_valid",
            "ck_invoices_invoice_status_valid",
            "ck_invoices_invoice_source_type_valid",
            "ck_invoices_invoice_non_negative_amounts",
            "ck_invoices_invoice_verified_requires_human_actor",
            "ck_invoices_invoice_soft_delete_unverified_only",
        }.issubset(invoice_checks)

        invoice_fks = {fk["name"] for fk in inspector.get_foreign_keys("invoices")}
        assert "fk_invoices_workspace_supplier" in invoice_fks
        assert "fk_invoices_workspace_document" in invoice_fks

        # Verify PostgreSQL actually enforces invoice check constraints inside a rolled-back transaction.
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                org_id = str(uuid.uuid4())
                ws_id = str(uuid.uuid4())
                user_id = str(uuid.uuid4())
                upload_day = date(2026, 4, 6)

                conn.execute(
                    text(
                        "INSERT INTO organizations (id, name, slug, firm_type, primary_contact_email) "
                        "VALUES (CAST(:id AS uuid), :name, :slug, :firm_type, :email)"
                    ),
                    {
                        "id": org_id,
                        "name": "Migration Test Firm",
                        "slug": f"migration-test-{org_id[:8]}",
                        "firm_type": "CA Practice",
                        "email": "test-firm@example.invalid",
                    },
                )
                conn.execute(
                    text(
                        "INSERT INTO workspaces (id, organization_id, name, workspace_code) "
                        "VALUES (CAST(:id AS uuid), CAST(:org_id AS uuid), :name, :code)"
                    ),
                    {
                        "id": ws_id,
                        "org_id": org_id,
                        "name": "Test Client Workspace",
                        "code": f"WS-{ws_id[:8]}",
                    },
                )
                conn.execute(
                    text(
                        "INSERT INTO users (id, email, full_name, password_hash) "
                        "VALUES (CAST(:id AS uuid), :email, :full_name, :password_hash)"
                    ),
                    {
                        "id": user_id,
                        "email": f"reviewer-{user_id[:8]}@example.invalid",
                        "full_name": "Migration Reviewer",
                        "password_hash": "test-only-non-login-placeholder-hash",
                    },
                )

                # 1. Human-actor gate must reject VERIFIED without verifier & timestamp
                with pytest.raises(IntegrityError) as verified_exc:
                    with conn.begin_nested():
                        conn.execute(
                            text(
                                "INSERT INTO invoices ("
                                "id, workspace_id, supplier_name_snapshot, buyer_name_snapshot, "
                                "invoice_number, normalized_invoice_number, upload_date, status"
                                ") VALUES ("
                                "CAST(:id AS uuid), CAST(:ws_id AS uuid), :supplier, :buyer, "
                                ":inv_no, :norm_inv_no, :upload_date, 'VERIFIED'"
                                ")"
                            ),
                            {
                                "id": str(uuid.uuid4()),
                                "ws_id": ws_id,
                                "supplier": "Test Supplier",
                                "buyer": "Test Buyer",
                                "inv_no": "INV-001",
                                "norm_inv_no": "inv-001",
                                "upload_date": upload_day,
                            },
                        )
                verified_diag = getattr(
                    getattr(verified_exc.value.orig, "diag", None),
                    "constraint_name",
                    None,
                )
                assert (
                    verified_diag == "ck_invoices_invoice_verified_requires_human_actor"
                    or "ck_invoices_invoice_verified_requires_human_actor"
                    in str(verified_exc.value)
                )

                # 2. Valid PENDING_REVIEW insert succeeds
                with conn.begin_nested():
                    conn.execute(
                        text(
                            "INSERT INTO invoices ("
                            "id, workspace_id, supplier_name_snapshot, buyer_name_snapshot, "
                            "invoice_number, normalized_invoice_number, upload_date, status"
                            ") VALUES ("
                            "CAST(:id AS uuid), CAST(:ws_id AS uuid), :supplier, :buyer, "
                            ":inv_no, :norm_inv_no, :upload_date, 'PENDING_REVIEW'"
                            ")"
                        ),
                        {
                            "id": str(uuid.uuid4()),
                            "ws_id": ws_id,
                            "supplier": "Test Supplier",
                            "buyer": "Test Buyer",
                            "inv_no": "INV-002",
                            "norm_inv_no": "inv-002",
                            "upload_date": upload_day,
                        },
                    )

                # 3. Soft-delete guard must reject deleted VERIFIED invoice
                with pytest.raises(IntegrityError) as delete_exc:
                    with conn.begin_nested():
                        conn.execute(
                            text(
                                "INSERT INTO invoices ("
                                "id, workspace_id, supplier_name_snapshot, buyer_name_snapshot, "
                                "invoice_number, normalized_invoice_number, upload_date, "
                                "status, verified_by_user_id, verified_at, deleted_at"
                                ") VALUES ("
                                "CAST(:id AS uuid), CAST(:ws_id AS uuid), :supplier, :buyer, "
                                ":inv_no, :norm_inv_no, :upload_date, "
                                "'VERIFIED', CAST(:user_id AS uuid), now(), now()"
                                ")"
                            ),
                            {
                                "id": str(uuid.uuid4()),
                                "ws_id": ws_id,
                                "supplier": "Test Supplier",
                                "buyer": "Test Buyer",
                                "inv_no": "INV-003",
                                "norm_inv_no": "inv-003",
                                "upload_date": upload_day,
                                "user_id": user_id,
                            },
                        )
                delete_diag = getattr(
                    getattr(delete_exc.value.orig, "diag", None),
                    "constraint_name",
                    None,
                )
                assert (
                    delete_diag == "ck_invoices_invoice_soft_delete_unverified_only"
                    or "ck_invoices_invoice_soft_delete_unverified_only"
                    in str(delete_exc.value)
                )

                # 4. Negative taxable amount must be rejected
                with pytest.raises(IntegrityError) as non_neg_exc:
                    with conn.begin_nested():
                        conn.execute(
                            text(
                                "INSERT INTO invoices ("
                                "id, workspace_id, supplier_name_snapshot, buyer_name_snapshot, "
                                "invoice_number, normalized_invoice_number, upload_date, taxable_amount"
                                ") VALUES ("
                                "CAST(:id AS uuid), CAST(:ws_id AS uuid), :supplier, :buyer, "
                                ":inv_no, :norm_inv_no, :upload_date, -1.00"
                                ")"
                            ),
                            {
                                "id": str(uuid.uuid4()),
                                "ws_id": ws_id,
                                "supplier": "Test Supplier",
                                "buyer": "Test Buyer",
                                "inv_no": "INV-004",
                                "norm_inv_no": "inv-004",
                                "upload_date": upload_day,
                            },
                        )
                non_neg_diag = getattr(
                    getattr(non_neg_exc.value.orig, "diag", None),
                    "constraint_name",
                    None,
                )
                assert (
                    non_neg_diag == "ck_invoices_invoice_non_negative_amounts"
                    or "ck_invoices_invoice_non_negative_amounts"
                    in str(non_neg_exc.value)
                )

                # 5. Invalid discount_mode must be rejected
                with pytest.raises(IntegrityError) as discount_exc:
                    with conn.begin_nested():
                        conn.execute(
                            text(
                                "INSERT INTO invoices ("
                                "id, workspace_id, supplier_name_snapshot, buyer_name_snapshot, "
                                "invoice_number, normalized_invoice_number, upload_date, discount_mode"
                                ") VALUES ("
                                "CAST(:id AS uuid), CAST(:ws_id AS uuid), :supplier, :buyer, "
                                ":inv_no, :norm_inv_no, :upload_date, 'INVALID_MODE'"
                                ")"
                            ),
                            {
                                "id": str(uuid.uuid4()),
                                "ws_id": ws_id,
                                "supplier": "Test Supplier",
                                "buyer": "Test Buyer",
                                "inv_no": "INV-005",
                                "norm_inv_no": "inv-005",
                                "upload_date": upload_day,
                            },
                        )
                discount_diag = getattr(
                    getattr(discount_exc.value.orig, "diag", None),
                    "constraint_name",
                    None,
                )
                assert (
                    discount_diag == "ck_invoices_invoice_discount_mode_valid"
                    or "ck_invoices_invoice_discount_mode_valid"
                    in str(discount_exc.value)
                )

                # 6. Documents scan_status allows FAILED and rejects invalid values
                doc_id = str(uuid.uuid4())
                with conn.begin_nested():
                    conn.execute(
                        text(
                            "INSERT INTO documents ("
                            "id, workspace_id, uploaded_by_user_id, original_filename, "
                            "storage_key, mime_type, byte_size, sha256_checksum, scan_status"
                            ") VALUES ("
                            "CAST(:id AS uuid), CAST(:ws_id AS uuid), CAST(:user_id AS uuid), "
                            ":fname, :skey, 'application/pdf', 128, :sha, 'FAILED'"
                            ")"
                        ),
                        {
                            "id": doc_id,
                            "ws_id": ws_id,
                            "user_id": user_id,
                            "fname": "scan-failed.pdf",
                            "skey": f"orgs/{org_id}/workspaces/{ws_id}/{doc_id}.pdf",
                            "sha": "a" * 64,
                        },
                    )

                with pytest.raises(IntegrityError) as doc_scan_exc:
                    with conn.begin_nested():
                        bad_doc_id = str(uuid.uuid4())
                        conn.execute(
                            text(
                                "INSERT INTO documents ("
                                "id, workspace_id, uploaded_by_user_id, original_filename, "
                                "storage_key, mime_type, byte_size, sha256_checksum, scan_status"
                                ") VALUES ("
                                "CAST(:id AS uuid), CAST(:ws_id AS uuid), CAST(:user_id AS uuid), "
                                ":fname, :skey, 'application/pdf', 128, :sha, 'INVALID_STATUS'"
                                ")"
                            ),
                            {
                                "id": bad_doc_id,
                                "ws_id": ws_id,
                                "user_id": user_id,
                                "fname": "scan-bad.pdf",
                                "skey": f"orgs/{org_id}/workspaces/{ws_id}/{bad_doc_id}.pdf",
                                "sha": "b" * 64,
                            },
                        )
                doc_scan_diag = getattr(
                    getattr(doc_scan_exc.value.orig, "diag", None),
                    "constraint_name",
                    None,
                )
                assert (
                    doc_scan_diag == "ck_documents_document_scan_status_valid"
                    or "ck_documents_document_scan_status_valid"
                    in str(doc_scan_exc.value)
                )
            finally:
                tx.rollback()

        command.downgrade(alembic_cfg, "base")
        inspector_after_down = inspect(engine)
        remaining = set(inspector_after_down.get_table_names())
        assert EXPECTED_TABLES.isdisjoint(remaining)

        command.upgrade(alembic_cfg, "head")
    finally:
        engine.dispose()


def test_migrations_use_op_f_for_check_constraints_matching_models() -> None:
    versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    migration_files = sorted(versions_dir.glob("*.py"))
    assert migration_files, "No Alembic migration files found."

    migration_checks: dict[str, set[str]] = {}
    for migration_path in migration_files:
        tree = ast.parse(migration_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "create_table"
                and node.args
            ):
                table_name = ast.literal_eval(node.args[0])
                table_check_names: set[str] = migration_checks.get(table_name, set())
                for arg in node.args[1:]:
                    if (
                        isinstance(arg, ast.Call)
                        and isinstance(arg.func, ast.Attribute)
                        and arg.func.attr == "CheckConstraint"
                    ):
                        name_kw = next(
                            (kw for kw in arg.keywords if kw.arg == "name"),
                            None,
                        )
                        assert name_kw is not None, (
                            f"CheckConstraint on {table_name} ({migration_path.name}) "
                            "must specify name=op.f(...)"
                        )
                        name_val = name_kw.value
                        assert (
                            isinstance(name_val, ast.Call)
                            and isinstance(name_val.func, ast.Attribute)
                            and isinstance(name_val.func.value, ast.Name)
                            and name_val.func.value.id == "op"
                            and name_val.func.attr == "f"
                            and len(name_val.args) == 1
                        ), (
                            f"CheckConstraint on {table_name} ({migration_path.name}) must wrap name "
                            "in op.f(...) to prevent MetaData naming_convention double-prefixing."
                        )
                        resolved_name = ast.literal_eval(name_val.args[0])
                        assert isinstance(resolved_name, str)
                        assert resolved_name.startswith(f"ck_{table_name}_")
                        assert not resolved_name.startswith(f"ck_{table_name}_ck_")
                        assert len(resolved_name) <= 63
                        table_check_names.add(resolved_name)
                if table_check_names:
                    migration_checks[table_name] = table_check_names

    expected_model_checks = {
        table_name: {
            constraint.name
            for constraint in table.constraints
            if isinstance(constraint, CheckConstraint) and constraint.name is not None
        }
        for table_name, table in Base.metadata.tables.items()
        if any(isinstance(constraint, CheckConstraint) for constraint in table.constraints)
    }
    assert migration_checks == expected_model_checks


def test_alembic_revision_ids_fit_alembic_version_and_linear_chain() -> None:
    versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    migration_files = sorted(versions_dir.glob("*.py"))
    assert len(migration_files) >= 2

    revisions: dict[str, str | None] = {}
    for migration_path in migration_files:
        tree = ast.parse(migration_path.read_text(encoding="utf-8"))
        rev: str | None = None
        down_rev: str | None = None
        saw_down_rev = False
        for stmt in tree.body:
            target_name: str | None = None
            value_node: ast.AST | None = None
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                target_name = stmt.target.id
                value_node = stmt.value
            elif (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
            ):
                target_name = stmt.targets[0].id
                value_node = stmt.value

            if target_name == "revision" and value_node is not None:
                rev = ast.literal_eval(value_node)
            elif target_name == "down_revision" and value_node is not None:
                down_rev = ast.literal_eval(value_node)
                saw_down_rev = True

        assert isinstance(rev, str) and rev
        assert len(rev) <= 32, (
            f"Alembic revision {rev!r} in {migration_path.name} exceeds VARCHAR(32) limit."
        )
        assert saw_down_rev
        assert rev not in revisions, f"Duplicate Alembic revision {rev!r}"
        revisions[rev] = down_rev

    roots = [rev for rev, down_rev in revisions.items() if down_rev is None]
    assert roots == ["0001_initial_foundation"]

    referenced_parents = {
        down_rev for down_rev in revisions.values() if down_rev is not None
    }
    assert referenced_parents.issubset(revisions.keys())
    heads = [rev for rev in revisions if rev not in referenced_parents]
    assert heads == ["0003_doc_failed_scan_status"]


# ---------------------------------------------------------------------------
# Pre-connection safety guard unit tests (must never connect or run Alembic)
# ---------------------------------------------------------------------------


def _install_no_execution_spies(monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbid_call(*args: object, **kwargs: object) -> None:
        raise AssertionError("Safety guard failed to block DB/Alembic execution.")

    current_module = sys.modules[__name__]
    monkeypatch.setattr(current_module, "create_engine", _forbid_call)
    monkeypatch.setattr(current_module.command, "downgrade", _forbid_call)
    monkeypatch.setattr(current_module.command, "upgrade", _forbid_call)


@pytest.mark.parametrize(
    "valid_url",
    [
        "postgresql+psycopg://postgres:ci_pass@localhost:5432/norus_billwise_test",
        "postgresql+psycopg://postgres:ci_pass@127.0.0.1:5432/norus_billwise_test",
        "postgresql+psycopg://postgres:ci_pass@[::1]:5432/norus_billwise_test",
        "postgresql://postgres:ci_pass@postgres:5432/norus_billwise_test",
    ],
)
def test_migration_guard_accepts_valid_local_and_ci_test_databases(
    valid_url: str,
) -> None:
    assert (
        validate_destructive_migration_target(
            valid_url,
            allow_destructive=True,
            require_postgres_tests=True,
        )
        == valid_url
    )


@pytest.mark.parametrize(
    ("unsafe_url", "expected_fragment"),
    [
        (
            "postgresql+psycopg://app:secret_pw@localhost:5432/norus_billwise",
            "norus_billwise_test",
        ),
        (
            "postgresql+psycopg://app:secret_pw@localhost:5432/norus_billwise_production",
            "norus_billwise_test",
        ),
        (
            "postgresql+psycopg://app:secret_pw@localhost:5432/norus_billwise_staging",
            "norus_billwise_test",
        ),
        (
            "postgresql+psycopg://app:secret_pw@localhost:5432/norus_billwise_development",
            "norus_billwise_test",
        ),
        (
            "postgresql+psycopg://postgres:secret_pw@localhost:5432/postgres",
            "norus_billwise_test",
        ),
        (
            "postgresql+psycopg://postgres:secret_pw@prod-db.internal:5432/norus_billwise_test",
            "unapproved host",
        ),
        (
            "sqlite:///./norus_billwise_test.db",
            "postgresql",
        ),
        (
            "not-a-valid-url",
            "postgresql",
        ),
        (
            "postgresql+psycopg://postgres:secret_pw@localhost:notaport/norus_billwise_test",
            "malformed",
        ),
        (
            "postgresql+psycopg://postgres:secret_pw@/norus_billwise_test",
            "missing database hostname",
        ),
    ],
)
def test_migration_guard_rejects_unsafe_or_malformed_urls_without_connecting(
    monkeypatch: pytest.MonkeyPatch,
    unsafe_url: str,
    expected_fragment: str,
) -> None:
    _install_no_execution_spies(monkeypatch)
    monkeypatch.setenv("TEST_DATABASE_URL", unsafe_url)
    monkeypatch.setenv("NORUS_ALLOW_DESTRUCTIVE_MIGRATION_TEST", "1")
    monkeypatch.delenv("NORUS_REQUIRE_POSTGRES_TESTS", raising=False)

    with pytest.raises(pytest.fail.Exception) as exc_info:
        test_alembic_upgrade_and_downgrade_on_postgresql(monkeypatch)

    message = str(exc_info.value)
    assert expected_fragment in message
    assert "secret_pw" not in message
    assert unsafe_url not in message


def test_migration_guard_skips_when_test_url_missing_and_not_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_no_execution_spies(monkeypatch)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.delenv("NORUS_ALLOW_DESTRUCTIVE_MIGRATION_TEST", raising=False)
    monkeypatch.delenv("NORUS_REQUIRE_POSTGRES_TESTS", raising=False)

    with pytest.raises(pytest.skip.Exception):
        test_alembic_upgrade_and_downgrade_on_postgresql(monkeypatch)


def test_migration_guard_rejects_missing_destructive_opt_in_without_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_no_execution_spies(monkeypatch)
    monkeypatch.setenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://postgres:secret_pw@localhost:5432/norus_billwise_test",
    )
    monkeypatch.delenv("NORUS_ALLOW_DESTRUCTIVE_MIGRATION_TEST", raising=False)
    monkeypatch.delenv("NORUS_REQUIRE_POSTGRES_TESTS", raising=False)

    with pytest.raises(pytest.fail.Exception) as exc_info:
        test_alembic_upgrade_and_downgrade_on_postgresql(monkeypatch)

    message = str(exc_info.value)
    assert "NORUS_ALLOW_DESTRUCTIVE_MIGRATION_TEST=1" in message
    assert "secret_pw" not in message


def test_migration_guard_fails_in_required_postgres_mode_when_url_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_no_execution_spies(monkeypatch)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("NORUS_ALLOW_DESTRUCTIVE_MIGRATION_TEST", "1")
    monkeypatch.setenv("NORUS_REQUIRE_POSTGRES_TESTS", "1")

    with pytest.raises(pytest.fail.Exception) as exc_info:
        test_alembic_upgrade_and_downgrade_on_postgresql(monkeypatch)

    assert "NORUS_REQUIRE_POSTGRES_TESTS=1" in str(exc_info.value)


def test_migration_guard_fails_not_skips_when_postgres_required_and_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://postgres:secret_pw@127.0.0.1:59999/norus_billwise_test",
    )
    monkeypatch.setenv("NORUS_ALLOW_DESTRUCTIVE_MIGRATION_TEST", "1")
    monkeypatch.setenv("NORUS_REQUIRE_POSTGRES_TESTS", "1")

    class _FailingEngine:
        def connect(self) -> object:
            raise SQLAlchemyError("simulated connection refused for secret_pw")

        def dispose(self) -> None:
            return None

    monkeypatch.setattr(
        sys.modules[__name__],
        "create_engine",
        lambda *args, **kwargs: _FailingEngine(),
    )

    with pytest.raises(pytest.fail.Exception) as exc_info:
        test_alembic_upgrade_and_downgrade_on_postgresql(monkeypatch)

    message = str(exc_info.value)
    assert "NORUS_REQUIRE_POSTGRES_TESTS=1" in message
    assert "secret_pw" not in message
