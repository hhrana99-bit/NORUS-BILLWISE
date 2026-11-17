from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

EXPECTED_TABLES = {
    "organizations",
    "users",
    "user_sessions",
    "workspaces",
    "workspace_settings",
    "organization_memberships",
    "workspace_memberships",
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

        invoice_checks = {
            ck["name"] for ck in inspector.get_check_constraints("invoices")
        }
        assert "ck_invoices_invoice_verified_requires_human_actor" in invoice_checks
        assert "ck_invoices_invoice_soft_delete_unverified_only" in invoice_checks

        invoice_fks = {fk["name"] for fk in inspector.get_foreign_keys("invoices")}
        assert "fk_invoices_workspace_supplier" in invoice_fks
        assert "fk_invoices_workspace_document" in invoice_fks

        command.downgrade(alembic_cfg, "base")
        inspector_after_down = inspect(engine)
        remaining = set(inspector_after_down.get_table_names())
        assert EXPECTED_TABLES.isdisjoint(remaining)

        command.upgrade(alembic_cfg, "head")
    finally:
        engine.dispose()


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
