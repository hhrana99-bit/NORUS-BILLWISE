from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal

from fastapi import status
from sqlalchemy import Select, and_, case, exists, func, literal, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import AppError
from app.models.accounting import Invoice
from app.models.review import InvoiceReviewFlag, ReviewAction
from app.models.tenancy import User, Workspace, WorkspaceSettings, utc_now
from app.schemas.invoices import InvoiceStatus, ReconciliationStatus
from app.schemas.reports import (
    ExceptionFlagSnippetDto,
    ExceptionItemDto,
    ExceptionLastActionDto,
    MonthlyTrendBucketDto,
    MonthlyTrendResponse,
    ReportExceptionsResponse,
    ReportSummaryResponse,
    TrendWindow,
)
from app.schemas.review import FlagCategory
from app.services.audit_service import record_audit_event
from app.services.reconciliation_service import (
    ZERO,
    determine_invoice_tax_type,
    quantize_money,
)

MAX_CSV_EXPORT_ROWS = 10_000
CSV_STREAM_BATCH_SIZE = 500

_SHORT_MONTH_NAMES = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)

_DIRECT_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n", "\v", "\f")
_LEADING_STRIP_CHARS = " \t\r\n\v\f" + "".join(chr(c) for c in range(1, 32))
_FORMULA_OPERATORS = ("=", "+", "-", "@")

CSV_HEADERS = (
    "Workspace",
    "Invoice Number",
    "Supplier Name",
    "Supplier GSTIN",
    "Invoice Date",
    "Due Date",
    "Upload Date",
    "Currency",
    "Tax Type",
    "Taxable Amount",
    "CGST",
    "SGST",
    "IGST",
    "Cess",
    "Total GST",
    "Round Off",
    "Total Amount",
    "Variance Amount",
    "Reconciliation Status",
    "Status",
    "Verified At",
    "Verified By",
    "Open Flag Count",
    "Duplicate Warning",
    "Reviewer Note",
)


def _escape_like_pattern(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _validate_date_range(date_from: date | None, date_to: date | None) -> None:
    if date_from is not None and date_to is not None and date_from > date_to:
        raise AppError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="VALIDATION_ERROR",
            message="dateFrom cannot be after dateTo.",
        )


def _normalize_currency_filter(currency: str | None) -> str | None:
    if currency is None:
        return None
    cleaned = currency.strip().upper()
    if not cleaned:
        return None
    if len(cleaned) != 3 or not cleaned.isalpha():
        raise AppError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="VALIDATION_ERROR",
            message="currency must be a 3-letter ISO currency code.",
        )
    return cleaned


def _get_default_workspace_currency(db: Session, workspace_id: uuid.UUID) -> str:
    default_currency = db.scalar(
        select(WorkspaceSettings.default_currency).where(
            WorkspaceSettings.workspace_id == workspace_id
        )
    )
    return default_currency or "INR"


def _resolve_single_report_currency(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    conditions: list[object],
    requested_currency: str | None,
) -> str:
    if requested_currency is not None:
        return requested_currency

    distinct_currencies = list(
        db.scalars(select(Invoice.currency).where(*conditions).distinct())  # type: ignore[arg-type]
    )
    if len(distinct_currencies) > 1:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="MIXED_CURRENCY_NOT_SUPPORTED",
            message=(
                "Workspace contains invoices in multiple currencies. "
                "Specify the 'currency' query parameter to compute aggregated totals safely."
            ),
            details={"currencies": sorted(distinct_currencies)},
        )
    if len(distinct_currencies) == 1:
        return str(distinct_currencies[0])
    return _get_default_workspace_currency(db, workspace_id)


def _build_base_invoice_conditions(
    *,
    workspace_id: uuid.UUID,
    date_from: date | None = None,
    date_to: date | None = None,
    currency: str | None = None,
    invoice_status: InvoiceStatus | None = None,
) -> list[object]:
    conditions: list[object] = [
        Invoice.workspace_id == workspace_id,
        Invoice.deleted_at.is_(None),
    ]
    if date_from is not None:
        conditions.append(Invoice.invoice_date.is_not(None))
        conditions.append(Invoice.invoice_date >= date_from)
    if date_to is not None:
        conditions.append(Invoice.invoice_date.is_not(None))
        conditions.append(Invoice.invoice_date <= date_to)
    if currency is not None:
        conditions.append(Invoice.currency == currency)
    if invoice_status is not None:
        conditions.append(Invoice.status == invoice_status)
    return conditions


def sanitize_csv_cell(value: str | None) -> str:
    """
    Neutralize spreadsheet formula-injection payloads on text cells per OWASP CSV guidance.

    Leading whitespace/control characters followed by '=', '+', '-', or '@' are prefixed
    with a leading apostrophe so spreadsheet engines treat the cell as plain text.
    """
    if value is None:
        return ""
    cleaned = str(value).replace("\x00", "")
    if not cleaned:
        return ""
    stripped = cleaned.lstrip(_LEADING_STRIP_CHARS)
    if cleaned.startswith(_DIRECT_FORMULA_PREFIXES) or stripped.startswith(
        _FORMULA_OPERATORS
    ):
        return f"'{cleaned}"
    return cleaned


def format_csv_decimal(value: Decimal | None) -> str:
    """Serialize fixed-point monetary values without corrupting valid negative signs."""
    if value is None:
        return "0.00"
    return f"{quantize_money(Decimal(value)):.2f}"


def get_report_summary(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    date_from: date | None = None,
    date_to: date | None = None,
    currency: str | None = None,
) -> ReportSummaryResponse:
    """Compute workspace-scoped summary metrics and tax aggregates with zero N+1 or join fan-out."""
    _validate_date_range(date_from, date_to)
    normalized_currency = _normalize_currency_filter(currency)
    conditions = _build_base_invoice_conditions(
        workspace_id=workspace_id,
        date_from=date_from,
        date_to=date_to,
        currency=normalized_currency,
    )
    resolved_currency = _resolve_single_report_currency(
        db,
        workspace_id=workspace_id,
        conditions=conditions,
        requested_currency=normalized_currency,
    )

    agg_row = db.execute(
        select(
            func.count(Invoice.id),
            func.coalesce(
                func.sum(case((Invoice.status == "PENDING_REVIEW", 1), else_=0)), 0
            ),
            func.coalesce(
                func.sum(case((Invoice.status == "VERIFIED", 1), else_=0)), 0
            ),
            func.coalesce(
                func.sum(case((Invoice.status == "FLAGGED", 1), else_=0)), 0
            ),
            func.coalesce(
                func.sum(
                    case(
                        (Invoice.status == "PENDING_REVIEW", Invoice.total_amount),
                        else_=ZERO,
                    )
                ),
                ZERO,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (Invoice.status == "VERIFIED", Invoice.total_amount),
                        else_=ZERO,
                    )
                ),
                ZERO,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (Invoice.status == "FLAGGED", Invoice.total_amount),
                        else_=ZERO,
                    )
                ),
                ZERO,
            ),
            func.coalesce(func.sum(Invoice.taxable_amount), ZERO),
            func.coalesce(func.sum(Invoice.cgst_amount), ZERO),
            func.coalesce(func.sum(Invoice.sgst_amount), ZERO),
            func.coalesce(func.sum(Invoice.igst_amount), ZERO),
            func.coalesce(func.sum(Invoice.cess_amount), ZERO),
            func.coalesce(func.sum(Invoice.total_amount), ZERO),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                Invoice.status != "VERIFIED",
                                or_(
                                    Invoice.reconciliation_status == "VARIANCE_DETECTED",
                                    Invoice.line_item_reconciliation_status
                                    == "VARIANCE_WARNING",
                                ),
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        ).where(*conditions)  # type: ignore[arg-type]
    ).one()

    open_flag_count = int(
        db.scalar(
            select(func.count(InvoiceReviewFlag.id))
            .select_from(InvoiceReviewFlag)
            .join(Invoice, Invoice.id == InvoiceReviewFlag.invoice_id)
            .where(
                InvoiceReviewFlag.workspace_id == workspace_id,
                InvoiceReviewFlag.status == "OPEN",
                *conditions,  # type: ignore[arg-type]
            )
        )
        or 0
    )

    total_invoices = int(agg_row[0] or 0)
    pending_count = int(agg_row[1] or 0)
    verified_count = int(agg_row[2] or 0)
    flagged_count = int(agg_row[3] or 0)

    total_taxable = quantize_money(Decimal(agg_row[7] or ZERO))
    total_cgst = quantize_money(Decimal(agg_row[8] or ZERO))
    total_sgst = quantize_money(Decimal(agg_row[9] or ZERO))
    total_igst = quantize_money(Decimal(agg_row[10] or ZERO))
    total_cess = quantize_money(Decimal(agg_row[11] or ZERO))
    total_gst = quantize_money(total_cgst + total_sgst + total_igst + total_cess)
    total_invoice_value = quantize_money(Decimal(agg_row[12] or ZERO))
    variance_invoice_count = int(agg_row[13] or 0)

    verification_rate_percent = (
        round((verified_count / total_invoices) * 100) if total_invoices > 0 else 0
    )

    return ReportSummaryResponse(
        workspace_id=workspace_id,
        currency=resolved_currency,
        date_from=date_from,
        date_to=date_to,
        total_invoices=total_invoices,
        pending_count=pending_count,
        verified_count=verified_count,
        flagged_count=flagged_count,
        verification_rate_percent=verification_rate_percent,
        pending_value=quantize_money(Decimal(agg_row[4] or ZERO)),
        verified_value=quantize_money(Decimal(agg_row[5] or ZERO)),
        flagged_value=quantize_money(Decimal(agg_row[6] or ZERO)),
        total_taxable_value=total_taxable,
        total_cgst=total_cgst,
        total_sgst=total_sgst,
        total_igst=total_igst,
        total_cess=total_cess,
        total_gst=total_gst,
        total_invoice_value=total_invoice_value,
        open_flag_count=open_flag_count,
        outstanding_review_count=pending_count + flagged_count,
        variance_invoice_count=variance_invoice_count,
    )


def _to_month_index(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def _from_month_index(index: int) -> tuple[int, int, str, str]:
    year, month_zero = divmod(index, 12)
    month = month_zero + 1
    month_key = f"{year:04d}-{month:02d}"
    label = f"{_SHORT_MONTH_NAMES[month - 1]} {str(year)[-2:]}"
    return year, month, month_key, label


def get_monthly_trend(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    window: TrendWindow = "6m",
    currency: str | None = None,
) -> MonthlyTrendResponse:
    """Return chronological zero-filled monthly invoice volume and totals."""
    normalized_currency = _normalize_currency_filter(currency)
    base_conditions = _build_base_invoice_conditions(
        workspace_id=workspace_id,
        currency=normalized_currency,
    )
    resolved_currency = _resolve_single_report_currency(
        db,
        workspace_id=workspace_id,
        conditions=base_conditions,
        requested_currency=normalized_currency,
    )

    excluded_count = int(
        db.scalar(
            select(func.count(Invoice.id)).where(
                *base_conditions,  # type: ignore[arg-type]
                Invoice.invoice_date.is_(None),
            )
        )
        or 0
    )

    month_expr = func.date_trunc("month", Invoice.invoice_date)
    grouped_rows = db.execute(
        select(
            month_expr.label("month_start"),
            func.count(Invoice.id),
            func.coalesce(
                func.sum(case((Invoice.status == "VERIFIED", 1), else_=0)), 0
            ),
            func.coalesce(
                func.sum(case((Invoice.status == "PENDING_REVIEW", 1), else_=0)), 0
            ),
            func.coalesce(
                func.sum(case((Invoice.status == "FLAGGED", 1), else_=0)), 0
            ),
            func.coalesce(func.sum(Invoice.total_amount), ZERO),
            func.coalesce(func.sum(Invoice.taxable_amount), ZERO),
            func.coalesce(
                func.sum(
                    Invoice.cgst_amount
                    + Invoice.sgst_amount
                    + Invoice.igst_amount
                    + Invoice.cess_amount
                ),
                ZERO,
            ),
        )
        .where(*base_conditions, Invoice.invoice_date.is_not(None))  # type: ignore[arg-type]
        .group_by(month_expr)
        .order_by(month_expr.asc())
    ).all()

    if not grouped_rows:
        return MonthlyTrendResponse(
            workspace_id=workspace_id,
            window=window,
            currency=resolved_currency,
            buckets=[],
            excluded_count=excluded_count,
            out_of_window_count=0,
        )

    month_map: dict[int, MonthlyTrendBucketDto] = {}
    min_idx: int | None = None
    max_idx: int | None = None

    for row in grouped_rows:
        month_start = row[0]
        if isinstance(month_start, datetime):
            year, month = month_start.year, month_start.month
        else:
            year, month = month_start.year, month_start.month
        idx = _to_month_index(year, month)
        if min_idx is None or idx < min_idx:
            min_idx = idx
        if max_idx is None or idx > max_idx:
            max_idx = idx

        _, _, month_key, label = _from_month_index(idx)
        month_map[idx] = MonthlyTrendBucketDto(
            month_key=month_key,
            label=label,
            total_count=int(row[1] or 0),
            verified_count=int(row[2] or 0),
            pending_count=int(row[3] or 0),
            flagged_count=int(row[4] or 0),
            total_value=quantize_money(Decimal(row[5] or ZERO)),
            total_taxable_value=quantize_money(Decimal(row[6] or ZERO)),
            total_gst=quantize_money(Decimal(row[7] or ZERO)),
        )

    assert min_idx is not None and max_idx is not None
    if window == "all":
        start_idx = min_idx
    elif window == "12m":
        start_idx = max_idx - 12 + 1
    else:
        start_idx = max_idx - 6 + 1

    out_of_window_count = sum(
        bucket.total_count for idx, bucket in month_map.items() if idx < start_idx
    )

    buckets: list[MonthlyTrendBucketDto] = []
    for idx in range(start_idx, max_idx + 1):
        existing = month_map.get(idx)
        if existing is not None:
            buckets.append(existing)
        else:
            _, _, month_key, label = _from_month_index(idx)
            buckets.append(
                MonthlyTrendBucketDto(
                    month_key=month_key,
                    label=label,
                    total_count=0,
                    verified_count=0,
                    pending_count=0,
                    flagged_count=0,
                    total_value=ZERO,
                    total_taxable_value=ZERO,
                    total_gst=ZERO,
                )
            )

    return MonthlyTrendResponse(
        workspace_id=workspace_id,
        window=window,
        currency=resolved_currency,
        buckets=buckets,
        excluded_count=excluded_count,
        out_of_window_count=out_of_window_count,
    )


def list_report_exceptions(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    search: str | None = None,
    status_filter: InvoiceStatus | None = None,
    flag_category: FlagCategory | None = None,
    reconciliation_status: ReconciliationStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 25,
) -> ReportExceptionsResponse:
    """List paginated FLAGGED + unresolved variance exceptions without N+1 queries."""
    _validate_date_range(date_from, date_to)

    exception_condition = or_(
        Invoice.status == "FLAGGED",
        and_(
            Invoice.status != "VERIFIED",
            or_(
                Invoice.reconciliation_status == "VARIANCE_DETECTED",
                Invoice.line_item_reconciliation_status == "VARIANCE_WARNING",
            ),
        ),
    )

    conditions: list[object] = [
        *_build_base_invoice_conditions(
            workspace_id=workspace_id,
            date_from=date_from,
            date_to=date_to,
            invoice_status=status_filter,
        ),
        exception_condition,
    ]

    if reconciliation_status is not None:
        conditions.append(Invoice.reconciliation_status == reconciliation_status)

    if flag_category is not None:
        conditions.append(
            exists(
                select(literal(1)).where(
                    InvoiceReviewFlag.workspace_id == workspace_id,
                    InvoiceReviewFlag.invoice_id == Invoice.id,
                    InvoiceReviewFlag.status == "OPEN",
                    InvoiceReviewFlag.flag_category == flag_category,
                )
            )
        )

    if search and search.strip():
        escaped = f"%{_escape_like_pattern(search.strip())}%"
        conditions.append(
            or_(
                Invoice.invoice_number.ilike(escaped, escape="\\"),
                Invoice.normalized_invoice_number.ilike(escaped, escape="\\"),
                Invoice.supplier_name_snapshot.ilike(escaped, escape="\\"),
                Invoice.supplier_gstin_snapshot.ilike(escaped, escape="\\"),
            )
        )

    total = int(
        db.scalar(select(func.count(Invoice.id)).where(*conditions)) or 0  # type: ignore[arg-type]
    )

    invoices = list(
        db.scalars(
            select(Invoice)
            .where(*conditions)  # type: ignore[arg-type]
            .order_by(
                case((Invoice.status == "FLAGGED", 0), else_=1).asc(),
                Invoice.updated_at.desc(),
                Invoice.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )

    if not invoices:
        return ReportExceptionsResponse(
            items=[],
            total=total,
            page=page,
            page_size=page_size,
        )

    invoice_ids = [inv.id for inv in invoices]

    open_flags_rows = list(
        db.scalars(
            select(InvoiceReviewFlag)
            .options(joinedload(InvoiceReviewFlag.created_by_user))
            .where(
                InvoiceReviewFlag.workspace_id == workspace_id,
                InvoiceReviewFlag.invoice_id.in_(invoice_ids),
                InvoiceReviewFlag.status == "OPEN",
            )
            .order_by(InvoiceReviewFlag.created_at.desc(), InvoiceReviewFlag.id.desc())
        )
    )
    open_flags_by_invoice: dict[uuid.UUID, list[InvoiceReviewFlag]] = {}
    for flag in open_flags_rows:
        open_flags_by_invoice.setdefault(flag.invoice_id, []).append(flag)

    latest_action_subq = (
        select(
            ReviewAction.id.label("action_id"),
            func.row_number()
            .over(
                partition_by=ReviewAction.invoice_id,
                order_by=(ReviewAction.created_at.desc(), ReviewAction.id.desc()),
            )
            .label("rn"),
        )
        .where(
            ReviewAction.workspace_id == workspace_id,
            ReviewAction.invoice_id.in_(invoice_ids),
        )
        .subquery()
    )
    latest_actions = list(
        db.scalars(
            select(ReviewAction)
            .options(joinedload(ReviewAction.actor_user))
            .join(
                latest_action_subq,
                ReviewAction.id == latest_action_subq.c.action_id,
            )
            .where(latest_action_subq.c.rn == 1)
        )
    )
    last_action_by_invoice: dict[uuid.UUID, ReviewAction] = {
        act.invoice_id: act for act in latest_actions
    }

    items: list[ExceptionItemDto] = []
    for inv in invoices:
        inv_flags = open_flags_by_invoice.get(inv.id, [])
        last_action = last_action_by_invoice.get(inv.id)
        items.append(
            ExceptionItemDto(
                invoice_id=inv.id,
                workspace_id=inv.workspace_id,
                supplier_id=inv.supplier_id,
                invoice_number=inv.invoice_number,
                supplier_name=inv.supplier_name_snapshot,
                supplier_gstin=inv.supplier_gstin_snapshot,
                invoice_date=inv.invoice_date,
                upload_date=inv.upload_date,
                currency=inv.currency,
                total_amount=quantize_money(Decimal(inv.total_amount)),
                variance_amount=quantize_money(Decimal(inv.variance_amount)),
                line_item_variance_amount=(
                    quantize_money(Decimal(inv.line_item_variance_amount))
                    if inv.line_item_variance_amount is not None
                    else None
                ),
                status=inv.status,  # type: ignore[arg-type]
                reconciliation_status=inv.reconciliation_status,  # type: ignore[arg-type]
                line_item_reconciliation_status=inv.line_item_reconciliation_status,  # type: ignore[arg-type]
                duplicate_warning=inv.duplicate_warning,
                open_flag_count=len(inv_flags),
                open_flags=[
                    ExceptionFlagSnippetDto(
                        id=flag.id,
                        flag_category=flag.flag_category,
                        reason_text=flag.reason_text,
                        created_by_name=(
                            flag.created_by_user.full_name
                            if flag.created_by_user is not None
                            else None
                        ),
                        created_at=flag.created_at,
                    )
                    for flag in inv_flags
                ],
                last_action=(
                    ExceptionLastActionDto(
                        id=last_action.id,
                        action_type=last_action.action_type,
                        actor_display_name=(
                            last_action.actor_user.full_name
                            if last_action.actor_user is not None
                            else "Reviewer"
                        ),
                        comment=last_action.comment,
                        created_at=last_action.created_at,
                    )
                    if last_action is not None
                    else None
                ),
                updated_at=inv.updated_at,
            )
        )

    return ReportExceptionsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


def _format_csv_row(row_values: tuple[str, ...]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(row_values)
    return buf.getvalue()


def _build_export_statement(
    *,
    workspace_id: uuid.UUID,
    conditions: list[object],
) -> Select[tuple[Invoice, int, str | None]]:
    open_flag_counts = (
        select(
            InvoiceReviewFlag.invoice_id.label("invoice_id"),
            func.count(InvoiceReviewFlag.id).label("open_flag_count"),
        )
        .where(
            InvoiceReviewFlag.workspace_id == workspace_id,
            InvoiceReviewFlag.status == "OPEN",
        )
        .group_by(InvoiceReviewFlag.invoice_id)
        .subquery()
    )
    return (
        select(
            Invoice,
            func.coalesce(open_flag_counts.c.open_flag_count, 0).label(
                "open_flag_count"
            ),
            User.full_name.label("verified_by_name"),
        )
        .outerjoin(open_flag_counts, open_flag_counts.c.invoice_id == Invoice.id)
        .outerjoin(User, User.id == Invoice.verified_by_user_id)
        .where(*conditions)  # type: ignore[arg-type]
        .order_by(
            Invoice.invoice_date.desc().nullslast(),
            Invoice.upload_date.desc(),
            Invoice.created_at.desc(),
            Invoice.id.desc(),
        )
    )


def prepare_and_stream_csv_export(
    db: Session,
    *,
    workspace: Workspace,
    actor: User,
    status_filter: InvoiceStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    currency: str | None = None,
    ip_address: str | None = None,
) -> tuple[str, Iterator[bytes]]:
    """
    Validate filters & row bounds, persist audit event, and return streaming RFC-4180 CSV generator.
    """
    _validate_date_range(date_from, date_to)
    normalized_currency = _normalize_currency_filter(currency)
    conditions = _build_base_invoice_conditions(
        workspace_id=workspace.id,
        date_from=date_from,
        date_to=date_to,
        currency=normalized_currency,
        invoice_status=status_filter,
    )

    row_count = int(
        db.scalar(select(func.count(Invoice.id)).where(*conditions)) or 0  # type: ignore[arg-type]
    )
    if row_count > MAX_CSV_EXPORT_ROWS:
        raise AppError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="EXPORT_ROW_LIMIT_EXCEEDED",
            message=(
                f"CSV export matched {row_count} invoices, exceeding the synchronous limit "
                f"of {MAX_CSV_EXPORT_ROWS} rows. Narrow your date or status filters."
            ),
            details={"rowCount": row_count, "maxRows": MAX_CSV_EXPORT_ROWS},
        )

    record_audit_event(
        db,
        organization_id=workspace.organization_id,
        workspace_id=workspace.id,
        actor_user=actor,
        event_type="report.csv_exported",
        entity_type="report",
        entity_id=None,
        summary=(
            f"Exported CSV report for workspace '{workspace.name}' "
            f"({row_count} invoice(s))."
        ),
        tone="neutral",
        metadata={
            "rowCount": row_count,
            "statusFilter": status_filter,
            "dateFrom": date_from.isoformat() if date_from is not None else None,
            "dateTo": date_to.isoformat() if date_to is not None else None,
            "currency": normalized_currency,
        },
        ip_address=ip_address,
    )
    db.commit()

    workspace_name_cell = sanitize_csv_cell(workspace.name)
    export_date_str = utc_now().date().isoformat()
    filename = f"norus-billwise-report-{export_date_str}.csv"
    stmt = _build_export_statement(workspace_id=workspace.id, conditions=conditions)

    def _csv_byte_stream() -> Iterator[bytes]:
        yield _format_csv_row(tuple(sanitize_csv_cell(h) for h in CSV_HEADERS)).encode(
            "utf-8"
        )
        result = db.execute(stmt.execution_options(yield_per=CSV_STREAM_BATCH_SIZE))
        for inv, open_flags, verified_by_name in result:
            cgst = quantize_money(Decimal(inv.cgst_amount))
            sgst = quantize_money(Decimal(inv.sgst_amount))
            igst = quantize_money(Decimal(inv.igst_amount))
            cess = quantize_money(Decimal(inv.cess_amount))
            total_gst = quantize_money(cgst + sgst + igst + cess)
            tax_type = determine_invoice_tax_type(
                cgst_amount=cgst, sgst_amount=sgst, igst_amount=igst
            )
            row = (
                workspace_name_cell,
                sanitize_csv_cell(inv.invoice_number),
                sanitize_csv_cell(inv.supplier_name_snapshot),
                sanitize_csv_cell(inv.supplier_gstin_snapshot or ""),
                inv.invoice_date.isoformat() if inv.invoice_date is not None else "",
                inv.due_date.isoformat() if inv.due_date is not None else "",
                inv.upload_date.isoformat(),
                sanitize_csv_cell(inv.currency),
                sanitize_csv_cell(tax_type),
                format_csv_decimal(inv.taxable_amount),
                format_csv_decimal(cgst),
                format_csv_decimal(sgst),
                format_csv_decimal(igst),
                format_csv_decimal(cess),
                format_csv_decimal(total_gst),
                format_csv_decimal(inv.round_off_amount),
                format_csv_decimal(inv.total_amount),
                format_csv_decimal(inv.variance_amount),
                sanitize_csv_cell(inv.reconciliation_status),
                sanitize_csv_cell(inv.status),
                inv.verified_at.isoformat() if inv.verified_at is not None else "",
                sanitize_csv_cell(verified_by_name or ""),
                str(int(open_flags or 0)),
                sanitize_csv_cell(inv.duplicate_warning or ""),
                sanitize_csv_cell(inv.reviewer_note or ""),
            )
            yield _format_csv_row(row).encode("utf-8")

    return filename, _csv_byte_stream()
