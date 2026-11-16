from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.tenancy import User, Workspace, utc_now

if TYPE_CHECKING:
    from app.models.review import InvoiceReviewFlag, ReviewAction


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("workspace_id", "normalized_name"),
        UniqueConstraint("workspace_id", "id", name="uq_suppliers_workspace_id_id"),
        Index(
            "uq_suppliers_workspace_gstin",
            "workspace_id",
            "gstin",
            unique=True,
            postgresql_where=text("gstin IS NOT NULL"),
        ),
        CheckConstraint(
            "status IN ('VERIFIED', 'NEEDS_VERIFICATION', 'FLAGGED')",
            name="supplier_status_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(240), nullable=False)
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    pan: Mapped[str | None] = mapped_column(String(10), nullable=True)
    state_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    state_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    category: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        server_default=text("'General'"),
        default="General",
    )
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'NEEDS_VERIFICATION'"),
        default="NEEDS_VERIFICATION",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=utc_now,
        onupdate=utc_now,
    )

    workspace: Mapped[Workspace] = relationship(back_populates="suppliers")
    invoices: Mapped[list[Invoice]] = relationship(
        back_populates="supplier",
        overlaps="workspace,invoices",
    )


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_documents_workspace_id_id"),
        CheckConstraint(
            "byte_size > 0 AND byte_size <= 15728640",
            name="document_byte_size_bounds",
        ),
        CheckConstraint("page_count >= 1", name="document_page_count_min"),
        CheckConstraint(
            "scan_status IN ('PENDING', 'CLEAN', 'INFECTED', 'SKIPPED_DEV')",
            name="document_scan_status_valid",
        ),
        Index("ix_documents_workspace_sha256", "workspace_id", "sha256_checksum"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    page_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1"), default=1
    )
    scan_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=text("'PENDING'"), default="PENDING"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=utc_now,
    )

    workspace: Mapped[Workspace] = relationship(back_populates="documents")
    uploaded_by_user: Mapped[User] = relationship()
    invoices: Mapped[list[Invoice]] = relationship(
        back_populates="document",
        overlaps="workspace,invoices,supplier",
    )


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_invoices_workspace_id_id"),
        ForeignKeyConstraint(
            ["workspace_id", "supplier_id"],
            ["suppliers.workspace_id", "suppliers.id"],
            ondelete="RESTRICT",
            name="fk_invoices_workspace_supplier",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "document_id"],
            ["documents.workspace_id", "documents.id"],
            ondelete="RESTRICT",
            name="fk_invoices_workspace_document",
        ),
        CheckConstraint(
            "discount_mode IN ('NONE', 'PRE_TAX', 'POST_TAX_COMMERCIAL')",
            name="invoice_discount_mode_valid",
        ),
        CheckConstraint(
            "reconciliation_status IN ('MATCHED', 'WITHIN_ROUNDING_TOLERANCE', 'VARIANCE_DETECTED', 'PENDING_INPUT')",
            name="invoice_reconciliation_status_valid",
        ),
        CheckConstraint(
            "line_item_reconciliation_status IN ('NO_LINE_ITEMS', 'MATCHED', 'VARIANCE_WARNING')",
            name="invoice_line_item_reconciliation_valid",
        ),
        CheckConstraint(
            "status IN ('PENDING_REVIEW', 'VERIFIED', 'FLAGGED')",
            name="invoice_status_valid",
        ),
        CheckConstraint(
            "source_type IN ('MANUAL_UPLOAD', 'MANUAL_ENTRY', 'OCR_EXTRACTED', 'SEED_DEMO')",
            name="invoice_source_type_valid",
        ),
        CheckConstraint(
            "taxable_amount >= 0 AND discount_amount >= 0 AND cgst_amount >= 0 "
            "AND sgst_amount >= 0 AND igst_amount >= 0 AND cess_amount >= 0 "
            "AND freight_amount >= 0 AND other_charges_amount >= 0 AND total_amount >= 0",
            name="invoice_non_negative_amounts",
        ),
        CheckConstraint(
            "(status != 'VERIFIED') OR (verified_by_user_id IS NOT NULL AND verified_at IS NOT NULL)",
            name="invoice_verified_requires_human_actor",
        ),
        CheckConstraint(
            "(deleted_at IS NULL) OR (status IN ('PENDING_REVIEW', 'FLAGGED'))",
            name="invoice_soft_delete_unverified_only",
        ),
        Index(
            "ix_invoices_workspace_status_date",
            "workspace_id",
            "status",
            text("invoice_date DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_invoices_workspace_supplier_invnum",
            "workspace_id",
            "supplier_id",
            "normalized_invoice_number",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Supplier & buyer snapshots
    supplier_name_snapshot: Mapped[str] = mapped_column(String(240), nullable=False)
    supplier_gstin_snapshot: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'PENDING-ENTRY'"),
        default="PENDING-ENTRY",
    )
    buyer_name_snapshot: Mapped[str] = mapped_column(String(240), nullable=False)
    buyer_gstin_snapshot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    place_of_supply_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    place_of_supply_name: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # Document metadata
    invoice_number: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_invoice_number: Mapped[str] = mapped_column(String(100), nullable=False)
    invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    upload_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'INR'"), default="INR"
    )
    is_reverse_charge: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )

    # Flexible financial breakdown (Decimal / NUMERIC only)
    taxable_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0.00"), default=Decimal("0.00")
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0.00"), default=Decimal("0.00")
    )
    discount_mode: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=text("'NONE'"), default="NONE"
    )
    cgst_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0.00"), default=Decimal("0.00")
    )
    sgst_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0.00"), default=Decimal("0.00")
    )
    igst_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0.00"), default=Decimal("0.00")
    )
    cess_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0.00"), default=Decimal("0.00")
    )
    freight_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0.00"), default=Decimal("0.00")
    )
    other_charges_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0.00"), default=Decimal("0.00")
    )
    round_off_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0.00"), default=Decimal("0.00")
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0.00"), default=Decimal("0.00")
    )

    # Reconciliation, advisory line-item checks & human review gate
    computed_expected_total: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0.00"), default=Decimal("0.00")
    )
    variance_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0.00"), default=Decimal("0.00")
    )
    reconciliation_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'PENDING_INPUT'"),
        default="PENDING_INPUT",
    )
    line_items_taxable_sum: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    line_item_variance_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    line_item_reconciliation_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'NO_LINE_ITEMS'"),
        default="NO_LINE_ITEMS",
    )
    line_item_warning: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default=text("'PENDING_REVIEW'"),
        default="PENDING_REVIEW",
    )
    duplicate_warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_note: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''"), default=""
    )
    source_type: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default=text("'MANUAL_UPLOAD'"),
        default="MANUAL_UPLOAD",
    )
    verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    deletion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=utc_now,
        onupdate=utc_now,
    )

    workspace: Mapped[Workspace] = relationship(
        back_populates="invoices",
        overlaps="supplier,document,invoices",
    )
    supplier: Mapped[Supplier | None] = relationship(
        back_populates="invoices",
        foreign_keys=[workspace_id, supplier_id],
        overlaps="workspace,document,invoices",
    )
    document: Mapped[Document | None] = relationship(
        back_populates="invoices",
        foreign_keys=[workspace_id, document_id],
        overlaps="workspace,supplier,invoices",
    )
    verified_by_user: Mapped[User | None] = relationship(
        foreign_keys=[verified_by_user_id]
    )
    deleted_by_user: Mapped[User | None] = relationship(
        foreign_keys=[deleted_by_user_id]
    )
    line_items: Mapped[list[InvoiceLineItem]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceLineItem.sort_order",
    )
    field_verifications: Mapped[list[InvoiceFieldVerification]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
    )
    review_flags: Mapped[list[InvoiceReviewFlag]] = relationship(
        back_populates="invoice"
    )
    review_actions: Mapped[list[ReviewAction]] = relationship(
        back_populates="invoice"
    )


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "invoice_id"],
            ["invoices.workspace_id", "invoices.id"],
            ondelete="CASCADE",
            name="fk_line_items_workspace_invoice",
        ),
        CheckConstraint(
            "quantity >= 0 AND tax_rate_percent >= 0 AND tax_rate_percent <= 100",
            name="line_item_quantity_tax_bounds",
        ),
        Index(
            "ix_invoice_line_items_order",
            "workspace_id",
            "invoice_id",
            "sort_order",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    hsn_sac: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("''"), default=""
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, server_default=text("1.0000"), default=Decimal("1.0000")
    )
    unit: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=text("'NOS'"), default="NOS"
    )
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, server_default=text("0.0000"), default=Decimal("0.0000")
    )
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0.00"), default=Decimal("0.00")
    )
    taxable_value: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0.00"), default=Decimal("0.00")
    )
    tax_rate_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("0.00"), default=Decimal("0.00")
    )
    cgst_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0.00"), default=Decimal("0.00")
    )
    sgst_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0.00"), default=Decimal("0.00")
    )
    igst_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0.00"), default=Decimal("0.00")
    )
    cess_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0.00"), default=Decimal("0.00")
    )
    line_total: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0.00"), default=Decimal("0.00")
    )

    invoice: Mapped[Invoice] = relationship(
        back_populates="line_items",
        foreign_keys=[workspace_id, invoice_id],
    )


class InvoiceFieldVerification(Base):
    __tablename__ = "invoice_field_verifications"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "invoice_id"],
            ["invoices.workspace_id", "invoices.id"],
            ondelete="CASCADE",
            name="fk_field_verifications_workspace_invoice",
        ),
        UniqueConstraint("invoice_id", "field_key"),
        CheckConstraint(
            "status IN ('VERIFIED', 'NEEDS_REVIEW', 'FLAGGED')",
            name="field_verification_status_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    field_key: Mapped[str] = mapped_column(String(48), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default=text("'NEEDS_REVIEW'"),
        default="NEEDS_REVIEW",
    )
    evidence_note: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''"), default=""
    )
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bounding_box: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    confidence_score: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 3), nullable=True
    )
    verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=utc_now,
        onupdate=utc_now,
    )

    invoice: Mapped[Invoice] = relationship(
        back_populates="field_verifications",
        foreign_keys=[workspace_id, invoice_id],
    )
    verified_by_user: Mapped[User | None] = relationship()
