from __future__ import annotations

from sqlalchemy import CheckConstraint, Numeric

import app.models  # noqa: F401 - ensure all models are registered
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


def test_all_tables_registered_on_metadata() -> None:
    assert len(EXPECTED_TABLES) == 17
    assert set(Base.metadata.tables.keys()) == EXPECTED_TABLES


def test_invoice_monetary_columns_use_exact_numeric_precision() -> None:
    invoices_table = Base.metadata.tables["invoices"]
    monetary_columns = [
        "taxable_amount",
        "discount_amount",
        "cgst_amount",
        "sgst_amount",
        "igst_amount",
        "cess_amount",
        "freight_amount",
        "other_charges_amount",
        "round_off_amount",
        "total_amount",
        "computed_expected_total",
        "variance_amount",
        "line_items_taxable_sum",
        "line_item_variance_amount",
    ]
    for col_name in monetary_columns:
        col_type = invoices_table.c[col_name].type
        assert isinstance(col_type, Numeric), f"{col_name} must use Numeric, got {col_type}"
        assert col_type.precision == 14
        assert col_type.scale == 2


def test_domain_check_constraints_and_composite_tenant_fks_exist() -> None:
    invoices_table = Base.metadata.tables["invoices"]
    ws_settings_table = Base.metadata.tables["workspace_settings"]

    invoice_checks = {
        constraint.name
        for constraint in invoices_table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert invoice_checks == {
        "ck_invoices_invoice_discount_mode_valid",
        "ck_invoices_invoice_reconciliation_status_valid",
        "ck_invoices_invoice_line_item_reconciliation_valid",
        "ck_invoices_invoice_status_valid",
        "ck_invoices_invoice_source_type_valid",
        "ck_invoices_invoice_non_negative_amounts",
        "ck_invoices_invoice_verified_requires_human_actor",
        "ck_invoices_invoice_soft_delete_unverified_only",
    }

    ws_checks = {
        constraint.name
        for constraint in ws_settings_table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert ws_checks == {
        "ck_workspace_settings_human_review_required",
        "ck_workspace_settings_rounding_tolerance_bounds",
    }

    invoice_fk_names = {fk.name for fk in invoices_table.foreign_key_constraints}
    assert "fk_invoices_workspace_supplier" in invoice_fk_names
    assert "fk_invoices_workspace_document" in invoice_fk_names

    flag_fk_names = {
        fk.name for fk in Base.metadata.tables["invoice_review_flags"].foreign_key_constraints
    }
    assert "fk_review_flags_workspace_invoice" in flag_fk_names

    action_fk_names = {
        fk.name for fk in Base.metadata.tables["review_actions"].foreign_key_constraints
    }
    assert "fk_review_actions_workspace_invoice" in action_fk_names


def test_metadata_check_constraints_have_no_duplicate_prefixes_and_fit_postgres_limit() -> None:
    for table_name, table in Base.metadata.tables.items():
        for constraint in table.constraints:
            if isinstance(constraint, CheckConstraint):
                assert constraint.name is not None
                assert constraint.name.startswith(f"ck_{table_name}_")
                assert not constraint.name.startswith(f"ck_{table_name}_ck_"), (
                    f"Duplicate ck_ prefix detected on {table_name}: {constraint.name}"
                )
                assert len(constraint.name) <= 63, (
                    f"PostgreSQL identifier exceeds 63 bytes: {constraint.name}"
                )


def test_audit_events_maps_event_metadata_to_metadata_column() -> None:
    audit_table = Base.metadata.tables["audit_events"]
    assert "metadata" in audit_table.c
    assert hasattr(app.models.AuditEvent, "event_metadata")
