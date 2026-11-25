from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_serializer

from app.schemas.base import ApiModel
from app.schemas.invoices import (
    InvoiceStatus,
    LineItemReconciliationStatus,
    ReconciliationStatus,
)
from app.schemas.review import FlagCategory

TrendWindow = Literal["6m", "12m", "all"]


class ReportSummaryResponse(ApiModel):
    workspace_id: uuid.UUID
    currency: str
    date_from: date | None
    date_to: date | None
    total_invoices: int
    pending_count: int
    verified_count: int
    flagged_count: int
    verification_rate_percent: int
    pending_value: Decimal
    verified_value: Decimal
    flagged_value: Decimal
    total_taxable_value: Decimal
    total_cgst: Decimal
    total_sgst: Decimal
    total_igst: Decimal
    total_cess: Decimal
    total_gst: Decimal
    total_invoice_value: Decimal
    open_flag_count: int
    outstanding_review_count: int
    variance_invoice_count: int
    is_statutory_filing_report: bool = False
    disclaimer: str = (
        "Operational workspace verification summary only; "
        "not a statutory GST return or audited ledger."
    )

    @field_serializer(
        "pending_value",
        "verified_value",
        "flagged_value",
        "total_taxable_value",
        "total_cgst",
        "total_sgst",
        "total_igst",
        "total_cess",
        "total_gst",
        "total_invoice_value",
    )
    def serialize_money(self, value: Decimal) -> str:
        return f"{value:.2f}"


class MonthlyTrendBucketDto(ApiModel):
    month_key: str
    label: str
    total_count: int
    verified_count: int
    pending_count: int
    flagged_count: int
    total_value: Decimal
    total_taxable_value: Decimal
    total_gst: Decimal

    @field_serializer("total_value", "total_taxable_value", "total_gst")
    def serialize_money(self, value: Decimal) -> str:
        return f"{value:.2f}"


class MonthlyTrendResponse(ApiModel):
    workspace_id: uuid.UUID
    window: TrendWindow
    currency: str
    buckets: list[MonthlyTrendBucketDto]
    excluded_count: int
    out_of_window_count: int = 0


class ExceptionFlagSnippetDto(ApiModel):
    id: uuid.UUID
    flag_category: FlagCategory | str
    reason_text: str
    created_by_name: str | None
    created_at: datetime


class ExceptionLastActionDto(ApiModel):
    id: uuid.UUID
    action_type: str
    actor_display_name: str
    comment: str | None
    created_at: datetime


class ExceptionItemDto(ApiModel):
    invoice_id: uuid.UUID
    workspace_id: uuid.UUID
    supplier_id: uuid.UUID | None
    invoice_number: str
    supplier_name: str
    supplier_gstin: str | None
    invoice_date: date | None
    upload_date: date
    currency: str
    total_amount: Decimal
    variance_amount: Decimal
    line_item_variance_amount: Decimal | None
    status: InvoiceStatus
    reconciliation_status: ReconciliationStatus
    line_item_reconciliation_status: LineItemReconciliationStatus
    duplicate_warning: str | None
    open_flag_count: int
    open_flags: list[ExceptionFlagSnippetDto] = Field(default_factory=list)
    last_action: ExceptionLastActionDto | None = None
    updated_at: datetime

    @field_serializer("total_amount", "variance_amount")
    def serialize_money(self, value: Decimal) -> str:
        return f"{value:.2f}"

    @field_serializer("line_item_variance_amount")
    def serialize_optional_money(self, value: Decimal | None) -> str | None:
        return f"{value:.2f}" if value is not None else None


class ReportExceptionsResponse(ApiModel):
    items: list[ExceptionItemDto]
    total: int
    page: int
    page_size: int
