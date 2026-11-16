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


def test_all_15_tables_registered_on_metadata() -> None:
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
    assert "ck_invoices_invoice_verified_requires_human_actor" in invoice_checks
    assert "ck_invoices_invoice_soft_delete_unverified_only" in invoice_checks
    assert "ck_invoices_invoice_line_item_reconciliation_valid" in invoice_checks

    ws_checks = {
        constraint.name
        for constraint in ws_settings_table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "ck_workspace_settings_human_review_required" in ws_checks

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


def test_audit_events_maps_event_metadata_to_metadata_column() -> None:
    audit_table = Base.metadata.tables["audit_events"]
    assert "metadata" in audit_table.c
    assert hasattr(app.models.AuditEvent, "event_metadata")
