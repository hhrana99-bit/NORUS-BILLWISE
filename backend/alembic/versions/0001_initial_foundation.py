"""Initial NORUS BILLWISE PostgreSQL foundation schema.

Revision ID: 0001_initial_foundation
Revises: None
Create Date: 2026-04-06 00:00:00+00:00

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_foundation"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. organizations
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("firm_type", sa.String(length=120), nullable=False),
        sa.Column("primary_contact_email", sa.String(length=255), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(trim(name)) > 0",
            name=op.f("ck_organizations_name_not_empty"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organizations"),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )

    # 2. users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.text("lower(email)")],
        unique=True,
    )

    # 3. user_sessions
    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "replaced_by_session_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_session_id"],
            ["user_sessions.id"],
            name="fk_user_sessions_replaced_by_session_id_user_sessions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_sessions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_sessions"),
        sa.UniqueConstraint(
            "refresh_token_hash",
            name="uq_user_sessions_refresh_token_hash",
        ),
    )
    op.create_index(
        "ix_user_sessions_id_revoked",
        "user_sessions",
        ["id", "revoked_at"],
        unique=False,
    )
    op.create_index(
        "ix_user_sessions_token_family",
        "user_sessions",
        ["token_family_id"],
        unique=False,
    )
    op.create_index(
        "ix_user_sessions_user_revoked",
        "user_sessions",
        ["user_id", "revoked_at"],
        unique=False,
    )

    # 4. workspaces
    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("workspace_code", sa.String(length=50), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_workspaces_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workspaces"),
        sa.UniqueConstraint(
            "organization_id",
            "workspace_code",
            name="uq_workspaces_organization_id_workspace_code",
        ),
    )

    # 5. workspace_settings
    op.create_table(
        "workspace_settings",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legal_entity_name", sa.String(length=240), nullable=False),
        sa.Column("company_gstin", sa.String(length=15), nullable=True),
        sa.Column("company_pan", sa.String(length=10), nullable=True),
        sa.Column(
            "registered_address",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column(
            "require_human_review",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "enable_duplicate_warnings",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "auto_flag_tax_mismatch",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "rounding_tolerance",
            sa.Numeric(precision=6, scale=2),
            server_default=sa.text("1.00"),
            nullable=False,
        ),
        sa.Column(
            "default_currency",
            sa.String(length=3),
            server_default=sa.text("'INR'"),
            nullable=False,
        ),
        sa.Column(
            "financial_year",
            sa.String(length=32),
            server_default=sa.text("'April - March'"),
            nullable=False,
        ),
        sa.Column(
            "date_format",
            sa.String(length=20),
            server_default=sa.text("'DD/MM/YYYY'"),
            nullable=False,
        ),
        sa.Column(
            "tax_regime",
            sa.String(length=64),
            server_default=sa.text("'India GST (CGST / SGST / IGST)'"),
            nullable=False,
        ),
        sa.Column(
            "notify_flagged_invoices",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "notify_daily_digest",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "notify_duplicate_alerts",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "require_human_review = true",
            name=op.f("ck_workspace_settings_human_review_required"),
        ),
        sa.CheckConstraint(
            "rounding_tolerance >= 0 AND rounding_tolerance <= 10.00",
            name=op.f("ck_workspace_settings_rounding_tolerance_bounds"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_workspace_settings_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("workspace_id", name="pk_workspace_settings"),
    )

    # 6. organization_memberships
    op.create_table(
        "organization_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'ACTIVE'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('ORG_OWNER', 'ORG_ADMIN', 'ORG_MEMBER')",
            name=op.f("ck_organization_memberships_org_membership_role_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'SUSPENDED')",
            name=op.f("ck_organization_memberships_org_membership_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_organization_memberships_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_organization_memberships_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organization_memberships"),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            name="uq_organization_memberships_organization_id_user_id",
        ),
    )

    # 7. workspace_memberships
    op.create_table(
        "workspace_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'ACTIVE'"),
            nullable=False,
        ),
        sa.Column(
            "invited_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('WORKSPACE_ADMIN', 'REVIEWER', 'UPLOADER', 'VIEWER')",
            name=op.f("ck_workspace_memberships_ws_membership_role_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'SUSPENDED')",
            name=op.f("ck_workspace_memberships_ws_membership_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"],
            ["users.id"],
            name="fk_workspace_memberships_invited_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_workspace_memberships_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_workspace_memberships_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workspace_memberships"),
        sa.UniqueConstraint(
            "workspace_id",
            "user_id",
            name="uq_workspace_memberships_workspace_id_user_id",
        ),
    )
    op.create_index(
        "ix_workspace_memberships_lookup",
        "workspace_memberships",
        ["user_id", "workspace_id", "status"],
        unique=False,
    )

    # 8. suppliers
    op.create_table(
        "suppliers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("normalized_name", sa.String(length=240), nullable=False),
        sa.Column("gstin", sa.String(length=15), nullable=True),
        sa.Column("pan", sa.String(length=10), nullable=True),
        sa.Column("state_code", sa.String(length=2), nullable=True),
        sa.Column("state_name", sa.String(length=80), nullable=True),
        sa.Column(
            "category",
            sa.String(length=120),
            server_default=sa.text("'General'"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'NEEDS_VERIFICATION'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('VERIFIED', 'NEEDS_VERIFICATION', 'FLAGGED')",
            name=op.f("ck_suppliers_supplier_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_suppliers_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_suppliers"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_suppliers_workspace_id_id"),
        sa.UniqueConstraint(
            "workspace_id",
            "normalized_name",
            name="uq_suppliers_workspace_id_normalized_name",
        ),
    )
    op.create_index(
        "uq_suppliers_workspace_gstin",
        "suppliers",
        ["workspace_id", "gstin"],
        unique=True,
        postgresql_where=sa.text("gstin IS NOT NULL"),
    )

    # 9. documents
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256_checksum", sa.String(length=64), nullable=False),
        sa.Column(
            "page_count",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "scan_status",
            sa.String(length=24),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "byte_size > 0 AND byte_size <= 15728640",
            name=op.f("ck_documents_document_byte_size_bounds"),
        ),
        sa.CheckConstraint(
            "page_count >= 1",
            name=op.f("ck_documents_document_page_count_min"),
        ),
        sa.CheckConstraint(
            "scan_status IN ('PENDING', 'CLEAN', 'INFECTED', 'SKIPPED_DEV')",
            name=op.f("ck_documents_document_scan_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["users.id"],
            name="fk_documents_uploaded_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_documents_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        sa.UniqueConstraint("storage_key", name="uq_documents_storage_key"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_documents_workspace_id_id"),
    )
    op.create_index(
        "ix_documents_workspace_sha256",
        "documents",
        ["workspace_id", "sha256_checksum"],
        unique=False,
    )

    # 10. invoices
    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("supplier_name_snapshot", sa.String(length=240), nullable=False),
        sa.Column(
            "supplier_gstin_snapshot",
            sa.String(length=20),
            server_default=sa.text("'PENDING-ENTRY'"),
            nullable=False,
        ),
        sa.Column("buyer_name_snapshot", sa.String(length=240), nullable=False),
        sa.Column("buyer_gstin_snapshot", sa.String(length=20), nullable=True),
        sa.Column("place_of_supply_code", sa.String(length=2), nullable=True),
        sa.Column("place_of_supply_name", sa.String(length=80), nullable=True),
        sa.Column("invoice_number", sa.String(length=100), nullable=False),
        sa.Column("normalized_invoice_number", sa.String(length=100), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("upload_date", sa.Date(), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default=sa.text("'INR'"),
            nullable=False,
        ),
        sa.Column(
            "is_reverse_charge",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "taxable_amount",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "discount_amount",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "discount_mode",
            sa.String(length=24),
            server_default=sa.text("'NONE'"),
            nullable=False,
        ),
        sa.Column(
            "cgst_amount",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "sgst_amount",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "igst_amount",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "cess_amount",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "freight_amount",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "other_charges_amount",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "round_off_amount",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "total_amount",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "computed_expected_total",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "variance_amount",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "reconciliation_status",
            sa.String(length=32),
            server_default=sa.text("'PENDING_INPUT'"),
            nullable=False,
        ),
        sa.Column(
            "line_items_taxable_sum",
            sa.Numeric(precision=14, scale=2),
            nullable=True,
        ),
        sa.Column(
            "line_item_variance_amount",
            sa.Numeric(precision=14, scale=2),
            nullable=True,
        ),
        sa.Column(
            "line_item_reconciliation_status",
            sa.String(length=32),
            server_default=sa.text("'NO_LINE_ITEMS'"),
            nullable=False,
        ),
        sa.Column("line_item_warning", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'PENDING_REVIEW'"),
            nullable=False,
        ),
        sa.Column("duplicate_warning", sa.Text(), nullable=True),
        sa.Column(
            "reviewer_note",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column(
            "source_type",
            sa.String(length=24),
            server_default=sa.text("'MANUAL_UPLOAD'"),
            nullable=False,
        ),
        sa.Column("verified_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("deletion_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(deleted_at IS NULL) OR (status IN ('PENDING_REVIEW', 'FLAGGED'))",
            name=op.f("ck_invoices_invoice_soft_delete_unverified_only"),
        ),
        sa.CheckConstraint(
            "(status != 'VERIFIED') OR (verified_by_user_id IS NOT NULL AND verified_at IS NOT NULL)",
            name=op.f("ck_invoices_invoice_verified_requires_human_actor"),
        ),
        sa.CheckConstraint(
            "discount_mode IN ('NONE', 'PRE_TAX', 'POST_TAX_COMMERCIAL')",
            name=op.f("ck_invoices_invoice_discount_mode_valid"),
        ),
        sa.CheckConstraint(
            "line_item_reconciliation_status IN ('NO_LINE_ITEMS', 'MATCHED', 'VARIANCE_WARNING')",
            name=op.f("ck_invoices_invoice_line_item_reconciliation_valid"),
        ),
        sa.CheckConstraint(
            "taxable_amount >= 0 AND discount_amount >= 0 AND cgst_amount >= 0 "
            "AND sgst_amount >= 0 AND igst_amount >= 0 AND cess_amount >= 0 "
            "AND freight_amount >= 0 AND other_charges_amount >= 0 AND total_amount >= 0",
            name=op.f("ck_invoices_invoice_non_negative_amounts"),
        ),
        sa.CheckConstraint(
            "reconciliation_status IN ('MATCHED', 'WITHIN_ROUNDING_TOLERANCE', 'VARIANCE_DETECTED', 'PENDING_INPUT')",
            name=op.f("ck_invoices_invoice_reconciliation_status_valid"),
        ),
        sa.CheckConstraint(
            "source_type IN ('MANUAL_UPLOAD', 'MANUAL_ENTRY', 'OCR_EXTRACTED', 'SEED_DEMO')",
            name=op.f("ck_invoices_invoice_source_type_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING_REVIEW', 'VERIFIED', 'FLAGGED')",
            name=op.f("ck_invoices_invoice_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["deleted_by_user_id"],
            ["users.id"],
            name="fk_invoices_deleted_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["verified_by_user_id"],
            ["users.id"],
            name="fk_invoices_verified_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "document_id"],
            ["documents.workspace_id", "documents.id"],
            name="fk_invoices_workspace_document",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "supplier_id"],
            ["suppliers.workspace_id", "suppliers.id"],
            name="fk_invoices_workspace_supplier",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_invoices_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_invoices"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_invoices_workspace_id_id"),
    )
    op.create_index(
        "ix_invoices_workspace_status_date",
        "invoices",
        ["workspace_id", "status", sa.text("invoice_date DESC")],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_invoices_workspace_supplier_invnum",
        "invoices",
        ["workspace_id", "supplier_id", "normalized_invoice_number"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # 11. invoice_line_items
    op.create_table(
        "invoice_line_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "sort_order",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "hsn_sac",
            sa.String(length=16),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column(
            "quantity",
            sa.Numeric(precision=14, scale=4),
            server_default=sa.text("1.0000"),
            nullable=False,
        ),
        sa.Column(
            "unit",
            sa.String(length=24),
            server_default=sa.text("'NOS'"),
            nullable=False,
        ),
        sa.Column(
            "unit_price",
            sa.Numeric(precision=14, scale=4),
            server_default=sa.text("0.0000"),
            nullable=False,
        ),
        sa.Column(
            "discount_amount",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "taxable_value",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "tax_rate_percent",
            sa.Numeric(precision=5, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "cgst_amount",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "sgst_amount",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "igst_amount",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "cess_amount",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.Column(
            "line_total",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "quantity >= 0 AND tax_rate_percent >= 0 AND tax_rate_percent <= 100",
            name=op.f("ck_invoice_line_items_line_item_quantity_tax_bounds"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "invoice_id"],
            ["invoices.workspace_id", "invoices.id"],
            name="fk_line_items_workspace_invoice",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_invoice_line_items"),
    )
    op.create_index(
        "ix_invoice_line_items_order",
        "invoice_line_items",
        ["workspace_id", "invoice_id", "sort_order"],
        unique=False,
    )

    # 12. invoice_field_verifications
    op.create_table(
        "invoice_field_verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field_key", sa.String(length=48), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'NEEDS_REVIEW'"),
            nullable=False,
        ),
        sa.Column(
            "evidence_note",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column(
            "bounding_box",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "confidence_score",
            sa.Numeric(precision=4, scale=3),
            nullable=True,
        ),
        sa.Column("verified_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('VERIFIED', 'NEEDS_REVIEW', 'FLAGGED')",
            name=op.f("ck_invoice_field_verifications_field_verification_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["verified_by_user_id"],
            ["users.id"],
            name="fk_invoice_field_verifications_verified_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "invoice_id"],
            ["invoices.workspace_id", "invoices.id"],
            name="fk_field_verifications_workspace_invoice",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_invoice_field_verifications"),
        sa.UniqueConstraint(
            "invoice_id",
            "field_key",
            name="uq_invoice_field_verifications_invoice_id_field_key",
        ),
    )

    # 13. invoice_review_flags
    op.create_table(
        "invoice_review_flags",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("flag_category", sa.String(length=64), nullable=False),
        sa.Column("reason_text", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'OPEN'"),
            nullable=False,
        ),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resolved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "char_length(trim(reason_text)) > 0",
            name=op.f("ck_invoice_review_flags_flag_reason_not_empty"),
        ),
        sa.CheckConstraint(
            "status IN ('OPEN', 'RESOLVED', 'DISMISSED')",
            name=op.f("ck_invoice_review_flags_flag_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_invoice_review_flags_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by_user_id"],
            ["users.id"],
            name="fk_invoice_review_flags_resolved_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "invoice_id"],
            ["invoices.workspace_id", "invoices.id"],
            name="fk_review_flags_workspace_invoice",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_invoice_review_flags"),
    )
    op.create_index(
        "ix_invoice_review_flags_lookup",
        "invoice_review_flags",
        ["workspace_id", "invoice_id", "status"],
        unique=False,
    )

    # 14. review_actions
    op.create_table(
        "review_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("previous_status", sa.String(length=24), nullable=False),
        sa.Column("new_status", sa.String(length=24), nullable=False),
        sa.Column(
            "variance_acknowledged",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "variance_amount_at_action",
            sa.Numeric(precision=14, scale=2),
            nullable=True,
        ),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "field_changes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_review_actions_actor_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "invoice_id"],
            ["invoices.workspace_id", "invoices.id"],
            name="fk_review_actions_workspace_invoice",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_review_actions"),
    )
    op.create_index(
        "ix_review_actions_lookup",
        "review_actions",
        ["workspace_id", "invoice_id", sa.text("created_at DESC")],
        unique=False,
    )

    # 15. audit_events
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_display_name", sa.String(length=160), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=48), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "tone",
            sa.String(length=16),
            server_default=sa.text("'neutral'"),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "tone IN ('neutral', 'success', 'warning')",
            name=op.f("ck_audit_events_audit_event_tone_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_audit_events_actor_user_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_audit_events_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_audit_events_workspace_id_workspaces",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
    )
    op.create_index(
        "ix_audit_events_org_created",
        "audit_events",
        ["organization_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_workspace_created",
        "audit_events",
        ["workspace_id", sa.text("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_workspace_created", table_name="audit_events")
    op.drop_index("ix_audit_events_org_created", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index("ix_review_actions_lookup", table_name="review_actions")
    op.drop_table("review_actions")

    op.drop_index(
        "ix_invoice_review_flags_lookup",
        table_name="invoice_review_flags",
    )
    op.drop_table("invoice_review_flags")

    op.drop_table("invoice_field_verifications")

    op.drop_index("ix_invoice_line_items_order", table_name="invoice_line_items")
    op.drop_table("invoice_line_items")

    op.drop_index(
        "ix_invoices_workspace_supplier_invnum",
        table_name="invoices",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index(
        "ix_invoices_workspace_status_date",
        table_name="invoices",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_table("invoices")

    op.drop_index("ix_documents_workspace_sha256", table_name="documents")
    op.drop_table("documents")

    op.drop_index(
        "uq_suppliers_workspace_gstin",
        table_name="suppliers",
        postgresql_where=sa.text("gstin IS NOT NULL"),
    )
    op.drop_table("suppliers")

    op.drop_index(
        "ix_workspace_memberships_lookup",
        table_name="workspace_memberships",
    )
    op.drop_table("workspace_memberships")

    op.drop_table("organization_memberships")
    op.drop_table("workspace_settings")
    op.drop_table("workspaces")

    op.drop_index("ix_user_sessions_user_revoked", table_name="user_sessions")
    op.drop_index("ix_user_sessions_token_family", table_name="user_sessions")
    op.drop_index("ix_user_sessions_id_revoked", table_name="user_sessions")
    op.drop_table("user_sessions")

    op.drop_index("uq_users_email_lower", table_name="users")
    op.drop_table("users")

    op.drop_table("organizations")
