from __future__ import annotations

import os
from pathlib import Path

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


def _get_postgres_test_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip(
            "TEST_DATABASE_URL is not set; skipping PostgreSQL Alembic migration test."
        )
    if not (
        url.startswith("postgresql+psycopg://") or url.startswith("postgresql://")
    ):
        pytest.skip("TEST_DATABASE_URL must point to PostgreSQL.")
    return url


def test_alembic_upgrade_and_downgrade_on_postgresql() -> None:
    db_url = _get_postgres_test_url()
    engine = create_engine(db_url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        engine.dispose()
        pytest.skip(f"PostgreSQL instance unavailable for migration test: {exc}")

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

        command.downgrade(alembic_cfg, "base")
        inspector_after_down = inspect(engine)
        remaining = set(inspector_after_down.get_table_names())
        assert EXPECTED_TABLES.isdisjoint(remaining)

        command.upgrade(alembic_cfg, "head")
    finally:
        engine.dispose()
