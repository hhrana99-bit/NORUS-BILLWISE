from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from fastapi import status
from pydantic.alias_generators import to_camel
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.errors import AppError
from app.models.accounting import (
    Document,
    Invoice,
    InvoiceFieldVerification,
    InvoiceLineItem,
    Supplier,
)
from app.models.review import InvoiceReviewFlag, ReviewAction
from app.models.tenancy import User, Workspace, WorkspaceSettings, utc_now
from app.schemas.invoices import (
    DuplicateMatchReason,
    InvoiceCreateRequest,
    InvoiceSortBy,
    InvoiceStatus,
    InvoiceUpdateRequest,
    LineItemReconciliationStatus,
    ReconciliationStatus,
    SortDirection,
    TaxTypeFilter,
    parse_financial_year_bounds,
)
from app.schemas.suppliers import normalize_supplier_name
from app.services.audit_service import record_audit_event
from app.services.reconciliation_service import (
    DEFAULT_ROUNDING_TOLERANCE,
    TWO_DP,
    ZERO,
    ReconciliationResult,
    compute_indian_financial_year,
    is_valid_indian_gstin,
    normalize_invoice_number,
    quantize_money,
    reconcile_invoice,
    resolve_existing_line_items,
    resolve_line_item_inputs,
)

_PLACEHOLDER_GSTINS = frozenset({"", "PENDING-ENTRY", "URD"})
_PLACEHOLDER_SUPPLIER_NAMES = frozenset(
    {"", "pending extraction", "unassigned supplier (manual entry required)"}
)
_DUPLICATE_AMOUNT_WINDOW_DAYS = 45
_DUPLICATE_NUMBER_CROSS_FY_DAYS = 180
_DRAFT_PLACEHOLDER_NORM_REGEX = re.compile(r"^draft-?[0-9a-f]{8}$")


@dataclass(frozen=True)
class DuplicateMatch:
    invoice_id: uuid.UUID
    invoice_number: str
    invoice_date: date | None
    total_amount: Decimal
    status: InvoiceStatus
    match_reasons: tuple[DuplicateMatchReason, ...]


@dataclass(frozen=True)
class InvoiceSummaryRow:
    invoice: Invoice
    line_item_count: int
    open_flag_count: int


@dataclass(frozen=True)
class InvoiceDetailRecord:
    invoice: Invoice
    open_flag_count: int
    reconciliation: ReconciliationResult
    duplicate_matches: tuple[DuplicateMatch, ...]


def is_placeholder_supplier_name(name: str) -> bool:
    return normalize_supplier_name(name) in _PLACEHOLDER_SUPPLIER_NAMES


def is_draft_placeholder_number(normalized_invoice_number: str) -> bool:
    return normalized_invoice_number.startswith("draft-") or bool(
        _DRAFT_PLACEHOLDER_NORM_REGEX.fullmatch(normalized_invoice_number)
    )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def get_workspace_settings(
    db: Session, workspace_id: uuid.UUID
) -> WorkspaceSettings | None:
    return db.scalar(
        select(WorkspaceSettings).where(
            WorkspaceSettings.workspace_id == workspace_id
        )
    )


_get_workspace_settings = get_workspace_settings


def _resolve_workspace_supplier(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    supplier_id: uuid.UUID,
) -> Supplier:
    supplier = db.scalar(
        select(Supplier).where(
            Supplier.id == supplier_id,
            Supplier.workspace_id == workspace_id,
        )
    )
    if supplier is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="SUPPLIER_NOT_FOUND",
            message="Supplier not found.",
        )
    return supplier


def _resolve_workspace_document(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
) -> Document:
    document = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.workspace_id == workspace_id,
        )
    )
    if document is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="DOCUMENT_NOT_FOUND",
            message="Document not found.",
        )
    if document.scan_status == "INFECTED":
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="DOCUMENT_INFECTED",
            message="An infected document cannot be linked to an invoice.",
        )
    if document.scan_status == "FAILED":
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="DOCUMENT_SCAN_FAILED",
            message="A document whose security scan failed cannot be linked to an invoice.",
        )
    return document


def _same_supplier_identity(
    *,
    cand_supplier_id: uuid.UUID | None,
    cand_supplier_gstin: str,
    cand_supplier_name: str,
    other: Invoice,
) -> bool:
    if cand_supplier_id is not None and other.supplier_id is not None:
        return cand_supplier_id == other.supplier_id

    cand_gstin = cand_supplier_gstin.strip().upper()
    other_gstin = (other.supplier_gstin_snapshot or "").strip().upper()
    if (
        cand_gstin not in _PLACEHOLDER_GSTINS
        and other_gstin not in _PLACEHOLDER_GSTINS
        and is_valid_indian_gstin(cand_gstin)
        and is_valid_indian_gstin(other_gstin)
    ):
        return cand_gstin == other_gstin

    cand_norm_name = (
        normalize_supplier_name(cand_supplier_name)
        if cand_supplier_name.strip()
        else ""
    )
    other_norm_name = (
        normalize_supplier_name(other.supplier_name_snapshot)
        if (other.supplier_name_snapshot or "").strip()
        else ""
    )
    if (
        cand_norm_name not in _PLACEHOLDER_SUPPLIER_NAMES
        and other_norm_name not in _PLACEHOLDER_SUPPLIER_NAMES
    ):
        return cand_norm_name == other_norm_name

    return False


def _invoice_dates_compatible_for_number_duplicate(
    cand_date: date | None,
    other_date: date | None,
) -> bool:
    """Guard against false duplicates when suppliers reset invoice numbering each financial year."""
    if cand_date is None or other_date is None:
        return True
    if compute_indian_financial_year(cand_date) == compute_indian_financial_year(
        other_date
    ):
        return True
    return abs((cand_date - other_date).days) <= _DUPLICATE_NUMBER_CROSS_FY_DAYS


def detect_advisory_duplicates(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    enable_duplicate_warnings: bool,
    exclude_invoice_id: uuid.UUID | None,
    supplier_id: uuid.UUID | None,
    supplier_gstin: str,
    supplier_name: str,
    normalized_invoice_number: str,
    invoice_date: date | None,
    total_amount: Decimal,
) -> tuple[list[DuplicateMatch], str | None]:
    """
    Detect potential duplicate active invoices in the same workspace without blocking entry.

    Rules (scoped strictly to workspace_id and deleted_at IS NULL):
    1. Same supplier identity + normalized invoice number (same Indian FY or within 180 days),
       ignoring blank 'draft-*' placeholders with zero total.
    2. Same supplier identity + total_amount > 0 within +/- INR 0.01 + invoice_date within 45 days.
    """
    if not enable_duplicate_warnings:
        return [], None

    cand_total = quantize_money(total_amount)
    is_zero_draft_placeholder = (
        is_draft_placeholder_number(normalized_invoice_number) and cand_total == ZERO
    )

    match_clauses = []
    if normalized_invoice_number and not is_zero_draft_placeholder:
        match_clauses.append(
            Invoice.normalized_invoice_number == normalized_invoice_number
        )
    if cand_total > ZERO and invoice_date is not None:
        window_start = invoice_date - timedelta(days=_DUPLICATE_AMOUNT_WINDOW_DAYS)
        window_end = invoice_date + timedelta(days=_DUPLICATE_AMOUNT_WINDOW_DAYS)
        match_clauses.append(
            and_(
                Invoice.total_amount.between(cand_total - TWO_DP, cand_total + TWO_DP),
                Invoice.invoice_date.is_not(None),
                Invoice.invoice_date.between(window_start, window_end),
            )
        )

    if not match_clauses:
        return [], None

    conditions = [
        Invoice.workspace_id == workspace_id,
        Invoice.deleted_at.is_(None),
        or_(*match_clauses),
    ]
    if exclude_invoice_id is not None:
        conditions.append(Invoice.id != exclude_invoice_id)

    candidates = list(
        db.scalars(
            select(Invoice)
            .where(*conditions)
            .order_by(Invoice.created_at.desc(), Invoice.id.asc())
            .limit(50)
        )
    )

    matches: list[DuplicateMatch] = []
    for other in candidates:
        if not _same_supplier_identity(
            cand_supplier_id=supplier_id,
            cand_supplier_gstin=supplier_gstin,
            cand_supplier_name=supplier_name,
            other=other,
        ):
            continue

        reasons: list[DuplicateMatchReason] = []
        if (
            not is_zero_draft_placeholder
            and normalized_invoice_number
            and other.normalized_invoice_number == normalized_invoice_number
            and _invoice_dates_compatible_for_number_duplicate(
                invoice_date, other.invoice_date
            )
        ):
            reasons.append("NORMALIZED_INVOICE_NUMBER")

        if (
            cand_total > ZERO
            and invoice_date is not None
            and other.invoice_date is not None
            and abs(quantize_money(other.total_amount) - cand_total) <= TWO_DP
            and abs((other.invoice_date - invoice_date).days)
            <= _DUPLICATE_AMOUNT_WINDOW_DAYS
        ):
            reasons.append("SIMILAR_TOTAL_WITHIN_45_DAYS")

        if reasons:
            matches.append(
                DuplicateMatch(
                    invoice_id=other.id,
                    invoice_number=other.invoice_number,
                    invoice_date=other.invoice_date,
                    total_amount=quantize_money(other.total_amount),
                    status=other.status,  # type: ignore[arg-type]
                    match_reasons=tuple(reasons),
                )
            )

    if not matches:
        return [], None

    matches.sort(
        key=lambda m: (
            0 if "NORMALIZED_INVOICE_NUMBER" in m.match_reasons else 1,
            m.invoice_number,
        )
    )
    primary = matches[0]
    suffix = (
        f" (+{len(matches) - 1} additional potential match)"
        if len(matches) == 2
        else (f" (+{len(matches) - 1} additional potential matches)" if len(matches) > 2 else "")
    )
    if "NORMALIZED_INVOICE_NUMBER" in primary.match_reasons:
        warning = (
            f"Potential duplicate invoice number matching '{primary.invoice_number}' "
            f"(INR {primary.total_amount:.2f}, {primary.status}){suffix}."
        )
    else:
        warning = (
            f"Similar amount (INR {primary.total_amount:.2f}) recorded on invoice "
            f"'{primary.invoice_number}' within 45 days ({primary.status}){suffix}."
        )
    return matches, warning


def _apply_reconciliation_to_invoice(
    invoice: Invoice, result: ReconciliationResult
) -> None:
    invoice.computed_expected_total = result.computed_expected_total
    invoice.variance_amount = result.variance_amount
    invoice.reconciliation_status = result.reconciliation_status
    invoice.line_items_taxable_sum = result.line_items_taxable_sum
    invoice.line_item_variance_amount = result.line_item_variance_amount
    invoice.line_item_reconciliation_status = result.line_item_reconciliation_status
    invoice.line_item_warning = result.line_item_warning


def _build_counts_subqueries(workspace_id: uuid.UUID):
    line_counts = (
        select(
            InvoiceLineItem.invoice_id.label("invoice_id"),
            func.count(InvoiceLineItem.id).label("line_item_count"),
        )
        .where(InvoiceLineItem.workspace_id == workspace_id)
        .group_by(InvoiceLineItem.invoice_id)
        .subquery()
    )
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
    return line_counts, open_flag_counts


def list_invoices(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    search: str | None = None,
    status_filter: InvoiceStatus | None = None,
    tax_type: TaxTypeFilter | None = None,
    supplier_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    reconciliation_status: ReconciliationStatus | None = None,
    line_item_reconciliation_status: LineItemReconciliationStatus | None = None,
    financial_year: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort_by: InvoiceSortBy = "uploadDate",
    sort_dir: SortDirection = "desc",
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[InvoiceSummaryRow], int]:
    """Search, filter, sort, and paginate active workspace invoices with bounded queries."""
    if date_from is not None and date_to is not None and date_from > date_to:
        raise AppError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="VALIDATION_ERROR",
            message="dateFrom cannot be later than dateTo.",
        )

    conditions = [
        Invoice.workspace_id == workspace_id,
        Invoice.deleted_at.is_(None),
    ]

    if status_filter is not None:
        conditions.append(Invoice.status == status_filter)
    if supplier_id is not None:
        conditions.append(Invoice.supplier_id == supplier_id)
    if document_id is not None:
        conditions.append(Invoice.document_id == document_id)
    if reconciliation_status is not None:
        conditions.append(Invoice.reconciliation_status == reconciliation_status)
    if line_item_reconciliation_status is not None:
        conditions.append(
            Invoice.line_item_reconciliation_status == line_item_reconciliation_status
        )

    if tax_type == "INTRA_STATE":
        conditions.append((Invoice.cgst_amount + Invoice.sgst_amount) > ZERO)
    elif tax_type == "INTER_STATE":
        conditions.append(Invoice.igst_amount > ZERO)

    if financial_year is not None and financial_year.strip():
        try:
            fy_start, fy_end = parse_financial_year_bounds(financial_year)
        except ValueError as exc:
            raise AppError(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="VALIDATION_ERROR",
                message=str(exc),
            ) from exc
        conditions.append(Invoice.invoice_date.is_not(None))
        conditions.append(Invoice.invoice_date >= fy_start)
        conditions.append(Invoice.invoice_date <= fy_end)

    if date_from is not None:
        conditions.append(Invoice.invoice_date.is_not(None))
        conditions.append(Invoice.invoice_date >= date_from)
    if date_to is not None:
        conditions.append(Invoice.invoice_date.is_not(None))
        conditions.append(Invoice.invoice_date <= date_to)

    cleaned_search = search.strip() if search is not None else ""
    if cleaned_search:
        pattern = f"%{_escape_like(cleaned_search)}%"
        norm_search = normalize_invoice_number(cleaned_search)
        norm_pattern = f"%{_escape_like(norm_search)}%" if norm_search else pattern
        conditions.append(
            or_(
                Invoice.invoice_number.ilike(pattern, escape="\\"),
                Invoice.normalized_invoice_number.ilike(norm_pattern, escape="\\"),
                Invoice.supplier_name_snapshot.ilike(pattern, escape="\\"),
                Invoice.supplier_gstin_snapshot.ilike(pattern, escape="\\"),
                Invoice.buyer_name_snapshot.ilike(pattern, escape="\\"),
                func.coalesce(Invoice.buyer_gstin_snapshot, "").ilike(
                    pattern, escape="\\"
                ),
            )
        )

    total = db.scalar(select(func.count(Invoice.id)).where(*conditions)) or 0

    tax_expr = (
        Invoice.cgst_amount
        + Invoice.sgst_amount
        + Invoice.igst_amount
        + Invoice.cess_amount
    )
    sort_expr_map = {
        "invoiceNumber": Invoice.invoice_number,
        "supplierName": Invoice.supplier_name_snapshot,
        "invoiceDate": Invoice.invoice_date,
        "totalAmount": Invoice.total_amount,
        "taxAmount": tax_expr,
        "status": Invoice.status,
        "uploadDate": Invoice.upload_date,
    }
    primary_col = sort_expr_map[sort_by]
    primary_order = (
        primary_col.asc() if sort_dir == "asc" else primary_col.desc()
    )
    if sort_by == "invoiceDate":
        primary_order = primary_order.nulls_last()

    line_counts, open_flag_counts = _build_counts_subqueries(workspace_id)
    stmt: Select[tuple[Invoice, int, int]] = (
        select(
            Invoice,
            func.coalesce(line_counts.c.line_item_count, 0).label("line_item_count"),
            func.coalesce(open_flag_counts.c.open_flag_count, 0).label(
                "open_flag_count"
            ),
        )
        .outerjoin(line_counts, line_counts.c.invoice_id == Invoice.id)
        .outerjoin(open_flag_counts, open_flag_counts.c.invoice_id == Invoice.id)
        .where(*conditions)
        .order_by(primary_order, Invoice.created_at.desc(), Invoice.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = db.execute(stmt).all()
    return [
        InvoiceSummaryRow(
            invoice=row[0],
            line_item_count=int(row[1] or 0),
            open_flag_count=int(row[2] or 0),
        )
        for row in rows
    ], int(total)


def load_active_invoice_detail(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    invoice_id: uuid.UUID,
    ws_settings: WorkspaceSettings | None = None,
) -> InvoiceDetailRecord:
    invoice = db.scalar(
        select(Invoice)
        .execution_options(populate_existing=True)
        .options(
            joinedload(Invoice.document),
            selectinload(Invoice.line_items),
            selectinload(Invoice.field_verifications),
            selectinload(Invoice.review_flags).joinedload(
                InvoiceReviewFlag.created_by_user
            ),
            selectinload(Invoice.review_flags).joinedload(
                InvoiceReviewFlag.resolved_by_user
            ),
        )
        .where(
            Invoice.id == invoice_id,
            Invoice.workspace_id == workspace_id,
            Invoice.deleted_at.is_(None),
        )
    )
    if invoice is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="INVOICE_NOT_FOUND",
            message="Invoice not found.",
        )

    open_flag_count = sum(1 for flag in invoice.review_flags if flag.status == "OPEN")

    resolved_settings = ws_settings or _get_workspace_settings(db, workspace_id)
    tolerance = (
        resolved_settings.rounding_tolerance
        if resolved_settings is not None
        else DEFAULT_ROUNDING_TOLERANCE
    )
    enable_dups = (
        resolved_settings.enable_duplicate_warnings
        if resolved_settings is not None
        else True
    )

    resolved_items = resolve_existing_line_items(invoice.line_items)
    recon = reconcile_invoice(
        taxable_amount=Decimal(invoice.taxable_amount),
        discount_amount=Decimal(invoice.discount_amount),
        discount_mode=invoice.discount_mode,
        cgst_amount=Decimal(invoice.cgst_amount),
        sgst_amount=Decimal(invoice.sgst_amount),
        igst_amount=Decimal(invoice.igst_amount),
        cess_amount=Decimal(invoice.cess_amount),
        freight_amount=Decimal(invoice.freight_amount),
        other_charges_amount=Decimal(invoice.other_charges_amount),
        round_off_amount=Decimal(invoice.round_off_amount),
        total_amount=Decimal(invoice.total_amount),
        rounding_tolerance=tolerance,
        line_items=resolved_items,
        supplier_gstin=invoice.supplier_gstin_snapshot,
        buyer_gstin=invoice.buyer_gstin_snapshot,
        place_of_supply_code=invoice.place_of_supply_code,
        is_reverse_charge=invoice.is_reverse_charge,
    )

    dup_matches, _ = detect_advisory_duplicates(
        db,
        workspace_id=workspace_id,
        enable_duplicate_warnings=enable_dups,
        exclude_invoice_id=invoice.id,
        supplier_id=invoice.supplier_id,
        supplier_gstin=invoice.supplier_gstin_snapshot,
        supplier_name=invoice.supplier_name_snapshot,
        normalized_invoice_number=invoice.normalized_invoice_number,
        invoice_date=invoice.invoice_date,
        total_amount=Decimal(invoice.total_amount),
    )

    return InvoiceDetailRecord(
        invoice=invoice,
        open_flag_count=int(open_flag_count),
        reconciliation=recon,
        duplicate_matches=tuple(dup_matches),
    )


_load_active_invoice_detail = load_active_invoice_detail


def get_invoice_detail(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    invoice_id: uuid.UUID,
) -> InvoiceDetailRecord:
    """Retrieve a single active workspace-scoped invoice with reconciliation and duplicates."""
    return load_active_invoice_detail(
        db,
        workspace_id=workspace_id,
        invoice_id=invoice_id,
    )


def create_invoice(
    db: Session,
    *,
    workspace: Workspace,
    actor: User,
    actor_role: str,
    payload: InvoiceCreateRequest,
    ip_address: str | None,
) -> InvoiceDetailRecord:
    """Create a workspace-scoped PENDING_REVIEW invoice with GST reconciliation and advisory duplicates."""
    if actor_role == "UPLOADER" and any(
        fv.status == "VERIFIED" for fv in payload.field_verifications
    ):
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN_ROLE",
            message="Uploaders cannot mark invoice field verifications as VERIFIED.",
        )

    ws_settings = _get_workspace_settings(db, workspace.id)

    supplier: Supplier | None = None
    if payload.supplier_id is not None:
        supplier = _resolve_workspace_supplier(
            db, workspace_id=workspace.id, supplier_id=payload.supplier_id
        )

    if payload.document_id is not None:
        _resolve_workspace_document(
            db, workspace_id=workspace.id, document_id=payload.document_id
        )

    supplier_name = (
        payload.supplier_name
        if payload.supplier_name is not None
        else (supplier.name if supplier is not None else "")
    )[:240]
    supplier_gstin = (
        payload.supplier_gstin
        if payload.supplier_gstin is not None
        else (supplier.gstin if supplier is not None and supplier.gstin else "PENDING-ENTRY")
    )[:20]

    default_buyer_name = (
        ws_settings.legal_entity_name if ws_settings is not None else workspace.name
    )[:240]
    buyer_name = (
        payload.buyer_name if payload.buyer_name is not None else default_buyer_name
    )[:240]
    buyer_gstin = (
        payload.buyer_gstin
        if "buyer_gstin" in payload.model_fields_set
        else (ws_settings.company_gstin if ws_settings is not None else None)
    )
    place_of_supply_code = payload.place_of_supply_code
    if place_of_supply_code is None and buyer_gstin and is_valid_indian_gstin(buyer_gstin):
        place_of_supply_code = buyer_gstin[:2]

    normalized_number = normalize_invoice_number(payload.invoice_number)
    upload_date = payload.upload_date or utc_now().date()
    source_type = payload.source_type or (
        "MANUAL_UPLOAD" if payload.document_id is not None else "MANUAL_ENTRY"
    )

    resolved_items = resolve_line_item_inputs(payload.line_items)
    tolerance = (
        ws_settings.rounding_tolerance
        if ws_settings is not None
        else DEFAULT_ROUNDING_TOLERANCE
    )
    recon = reconcile_invoice(
        taxable_amount=payload.taxable_amount,
        discount_amount=payload.discount_amount,
        discount_mode=payload.discount_mode,
        cgst_amount=payload.cgst_amount,
        sgst_amount=payload.sgst_amount,
        igst_amount=payload.igst_amount,
        cess_amount=payload.cess_amount,
        freight_amount=payload.freight_amount,
        other_charges_amount=payload.other_charges_amount,
        round_off_amount=payload.round_off_amount,
        total_amount=payload.total_amount,
        rounding_tolerance=tolerance,
        line_items=resolved_items,
        supplier_gstin=supplier_gstin,
        buyer_gstin=buyer_gstin,
        place_of_supply_code=place_of_supply_code,
        is_reverse_charge=payload.is_reverse_charge,
    )

    enable_dups = (
        ws_settings.enable_duplicate_warnings if ws_settings is not None else True
    )
    dup_matches, duplicate_warning = detect_advisory_duplicates(
        db,
        workspace_id=workspace.id,
        enable_duplicate_warnings=enable_dups,
        exclude_invoice_id=None,
        supplier_id=supplier.id if supplier is not None else None,
        supplier_gstin=supplier_gstin,
        supplier_name=supplier_name,
        normalized_invoice_number=normalized_number,
        invoice_date=payload.invoice_date,
        total_amount=quantize_money(payload.total_amount),
    )

    # Human review gate: POST always starts in PENDING_REVIEW regardless of input.
    invoice = Invoice(
        workspace_id=workspace.id,
        supplier_id=supplier.id if supplier is not None else None,
        document_id=payload.document_id,
        supplier_name_snapshot=supplier_name,
        supplier_gstin_snapshot=supplier_gstin,
        buyer_name_snapshot=buyer_name,
        buyer_gstin_snapshot=buyer_gstin,
        place_of_supply_code=place_of_supply_code,
        place_of_supply_name=payload.place_of_supply_name,
        invoice_number=payload.invoice_number,
        normalized_invoice_number=normalized_number,
        invoice_date=payload.invoice_date,
        due_date=payload.due_date,
        upload_date=upload_date,
        currency=payload.currency,
        is_reverse_charge=payload.is_reverse_charge,
        taxable_amount=quantize_money(payload.taxable_amount),
        discount_amount=quantize_money(payload.discount_amount),
        discount_mode=payload.discount_mode,
        cgst_amount=quantize_money(payload.cgst_amount),
        sgst_amount=quantize_money(payload.sgst_amount),
        igst_amount=quantize_money(payload.igst_amount),
        cess_amount=quantize_money(payload.cess_amount),
        freight_amount=quantize_money(payload.freight_amount),
        other_charges_amount=quantize_money(payload.other_charges_amount),
        round_off_amount=quantize_money(payload.round_off_amount),
        total_amount=quantize_money(payload.total_amount),
        status="PENDING_REVIEW",
        duplicate_warning=duplicate_warning,
        reviewer_note=payload.reviewer_note,
        source_type=source_type,
        verified_by_user_id=None,
        verified_at=None,
    )
    _apply_reconciliation_to_invoice(invoice, recon)

    db.add(invoice)
    db.flush()

    for li in resolved_items:
        db.add(
            InvoiceLineItem(
                workspace_id=workspace.id,
                invoice_id=invoice.id,
                sort_order=li.sort_order,
                description=li.description,
                hsn_sac=li.hsn_sac,
                quantity=li.quantity,
                unit=li.unit,
                unit_price=li.unit_price,
                discount_amount=li.discount_amount,
                taxable_value=li.taxable_value,
                tax_rate_percent=li.tax_rate_percent,
                cgst_amount=li.cgst_amount,
                sgst_amount=li.sgst_amount,
                igst_amount=li.igst_amount,
                cess_amount=li.cess_amount,
                line_total=li.line_total,
            )
        )

    for fv in payload.field_verifications:
        db.add(
            InvoiceFieldVerification(
                workspace_id=workspace.id,
                invoice_id=invoice.id,
                field_key=fv.field_key,
                status=fv.status,
                evidence_note=fv.evidence_note,
                source_page=fv.source_page,
                bounding_box=fv.bounding_box,
                confidence_score=fv.confidence_score,
                verified_by_user_id=actor.id if fv.status == "VERIFIED" else None,
            )
        )

    db.flush()

    record_audit_event(
        db,
        organization_id=workspace.organization_id,
        workspace_id=workspace.id,
        actor_user=actor,
        event_type="invoice.created",
        entity_type="invoice",
        entity_id=invoice.id,
        summary=f"Created invoice '{invoice.invoice_number}' ({invoice.status}).",
        tone="warning" if duplicate_warning else "neutral",
        metadata={
            "invoiceId": str(invoice.id),
            "status": invoice.status,
            "reconciliationStatus": invoice.reconciliation_status,
            "lineItemReconciliationStatus": invoice.line_item_reconciliation_status,
            "hasDuplicateWarning": duplicate_warning is not None,
            "duplicateMatchCount": len(dup_matches),
            "hasDocument": invoice.document_id is not None,
            "hasSupplier": invoice.supplier_id is not None,
        },
        ip_address=ip_address,
    )
    db.commit()
    db.expire(invoice)

    return _load_active_invoice_detail(
        db,
        workspace_id=workspace.id,
        invoice_id=invoice.id,
        ws_settings=ws_settings,
    )


def update_invoice(
    db: Session,
    *,
    workspace: Workspace,
    invoice_id: uuid.UUID,
    actor: User,
    actor_role: str,
    payload: InvoiceUpdateRequest,
    ip_address: str | None,
) -> InvoiceDetailRecord:
    """Update editable fields/line-items on an unverified invoice and recompute reconciliation."""
    if (
        actor_role == "UPLOADER"
        and payload.field_verifications is not None
        and any(fv.status == "VERIFIED" for fv in payload.field_verifications)
    ):
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN_ROLE",
            message="Uploaders cannot mark invoice field verifications as VERIFIED.",
        )

    invoice = db.scalar(
        select(Invoice)
        .where(
            Invoice.id == invoice_id,
            Invoice.workspace_id == workspace.id,
            Invoice.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if invoice is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="INVOICE_NOT_FOUND",
            message="Invoice not found.",
        )

    if invoice.status == "VERIFIED":
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="VERIFIED_INVOICE_LOCKED",
            message="Verified invoices are locked and must be reopened before editing.",
        )

    if actor_role == "UPLOADER" and invoice.status != "PENDING_REVIEW":
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN_ROLE",
            message="Uploaders can only edit invoices in PENDING_REVIEW status.",
        )

    updates = payload.model_dump(exclude_unset=True)
    changed_fields: list[str] = []

    new_supplier: Supplier | None = None
    if "supplier_id" in updates:
        if payload.supplier_id is not None:
            new_supplier = _resolve_workspace_supplier(
                db, workspace_id=workspace.id, supplier_id=payload.supplier_id
            )
            if invoice.supplier_id != new_supplier.id:
                changed_fields.append("supplierId")
            invoice.supplier_id = new_supplier.id
            if "supplier_name" not in updates:
                invoice.supplier_name_snapshot = new_supplier.name[:240]
                changed_fields.append("supplierName")
            if "supplier_gstin" not in updates:
                invoice.supplier_gstin_snapshot = (
                    new_supplier.gstin or "PENDING-ENTRY"
                )[:20]
                changed_fields.append("supplierGstin")
        else:
            if invoice.supplier_id is not None:
                changed_fields.append("supplierId")
            invoice.supplier_id = None

    if "document_id" in updates:
        if payload.document_id is not None:
            _resolve_workspace_document(
                db, workspace_id=workspace.id, document_id=payload.document_id
            )
        if invoice.document_id != payload.document_id:
            changed_fields.append("documentId")
        invoice.document_id = payload.document_id

    if "supplier_name" in updates and payload.supplier_name is not None:
        val = payload.supplier_name[:240]
        if invoice.supplier_name_snapshot != val:
            changed_fields.append("supplierName")
        invoice.supplier_name_snapshot = val

    if "supplier_gstin" in updates:
        resolved_sup_gstin = (payload.supplier_gstin or "PENDING-ENTRY")[:20]
        if invoice.supplier_gstin_snapshot != resolved_sup_gstin:
            changed_fields.append("supplierGstin")
        invoice.supplier_gstin_snapshot = resolved_sup_gstin

    if "buyer_name" in updates and payload.buyer_name is not None:
        val = payload.buyer_name[:240]
        if invoice.buyer_name_snapshot != val:
            changed_fields.append("buyerName")
        invoice.buyer_name_snapshot = val

    if "buyer_gstin" in updates:
        if invoice.buyer_gstin_snapshot != payload.buyer_gstin:
            changed_fields.append("buyerGstin")
        invoice.buyer_gstin_snapshot = payload.buyer_gstin

    simple_fields = (
        "place_of_supply_code",
        "place_of_supply_name",
        "invoice_number",
        "invoice_date",
        "due_date",
        "upload_date",
        "currency",
        "is_reverse_charge",
        "discount_mode",
        "reviewer_note",
    )
    for field_name in simple_fields:
        if field_name in updates:
            new_val = updates[field_name]
            if getattr(invoice, field_name) != new_val:
                changed_fields.append(to_camel(field_name))
            setattr(invoice, field_name, new_val)

    money_fields = (
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
    )
    for field_name in money_fields:
        if field_name in updates and updates[field_name] is not None:
            quantized = quantize_money(updates[field_name])
            if Decimal(getattr(invoice, field_name)) != quantized:
                changed_fields.append(to_camel(field_name))
            setattr(invoice, field_name, quantized)

    if (
        invoice.invoice_date is not None
        and invoice.due_date is not None
        and invoice.due_date < invoice.invoice_date
    ):
        db.rollback()
        raise AppError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="VALIDATION_ERROR",
            message="dueDate cannot be earlier than invoiceDate.",
        )

    invoice.normalized_invoice_number = normalize_invoice_number(invoice.invoice_number)

    if payload.line_items is not None:
        changed_fields.append("lineItems")
        resolved_items = resolve_line_item_inputs(payload.line_items)
        existing_items = list(
            db.scalars(
                select(InvoiceLineItem).where(
                    InvoiceLineItem.workspace_id == workspace.id,
                    InvoiceLineItem.invoice_id == invoice.id,
                )
            )
        )
        for existing in existing_items:
            db.delete(existing)
        db.flush()
        for li in resolved_items:
            db.add(
                InvoiceLineItem(
                    workspace_id=workspace.id,
                    invoice_id=invoice.id,
                    sort_order=li.sort_order,
                    description=li.description,
                    hsn_sac=li.hsn_sac,
                    quantity=li.quantity,
                    unit=li.unit,
                    unit_price=li.unit_price,
                    discount_amount=li.discount_amount,
                    taxable_value=li.taxable_value,
                    tax_rate_percent=li.tax_rate_percent,
                    cgst_amount=li.cgst_amount,
                    sgst_amount=li.sgst_amount,
                    igst_amount=li.igst_amount,
                    cess_amount=li.cess_amount,
                    line_total=li.line_total,
                )
            )
    else:
        existing_items = list(
            db.scalars(
                select(InvoiceLineItem)
                .where(
                    InvoiceLineItem.workspace_id == workspace.id,
                    InvoiceLineItem.invoice_id == invoice.id,
                )
                .order_by(InvoiceLineItem.sort_order.asc())
            )
        )
        resolved_items = resolve_existing_line_items(existing_items)

    if payload.field_verifications is not None:
        changed_fields.append("fieldVerifications")
        existing_fvs = {
            fv.field_key: fv
            for fv in db.scalars(
                select(InvoiceFieldVerification).where(
                    InvoiceFieldVerification.workspace_id == workspace.id,
                    InvoiceFieldVerification.invoice_id == invoice.id,
                )
            )
        }
        for fv_in in payload.field_verifications:
            target = existing_fvs.get(fv_in.field_key)
            if target is None:
                db.add(
                    InvoiceFieldVerification(
                        workspace_id=workspace.id,
                        invoice_id=invoice.id,
                        field_key=fv_in.field_key,
                        status=fv_in.status,
                        evidence_note=fv_in.evidence_note,
                        source_page=fv_in.source_page,
                        bounding_box=fv_in.bounding_box,
                        confidence_score=fv_in.confidence_score,
                        verified_by_user_id=(
                            actor.id if fv_in.status == "VERIFIED" else None
                        ),
                    )
                )
            else:
                target.status = fv_in.status
                target.evidence_note = fv_in.evidence_note
                target.source_page = fv_in.source_page
                target.bounding_box = fv_in.bounding_box
                target.confidence_score = fv_in.confidence_score
                target.verified_by_user_id = (
                    actor.id if fv_in.status == "VERIFIED" else None
                )

    ws_settings = _get_workspace_settings(db, workspace.id)
    tolerance = (
        ws_settings.rounding_tolerance
        if ws_settings is not None
        else DEFAULT_ROUNDING_TOLERANCE
    )
    recon = reconcile_invoice(
        taxable_amount=Decimal(invoice.taxable_amount),
        discount_amount=Decimal(invoice.discount_amount),
        discount_mode=invoice.discount_mode,
        cgst_amount=Decimal(invoice.cgst_amount),
        sgst_amount=Decimal(invoice.sgst_amount),
        igst_amount=Decimal(invoice.igst_amount),
        cess_amount=Decimal(invoice.cess_amount),
        freight_amount=Decimal(invoice.freight_amount),
        other_charges_amount=Decimal(invoice.other_charges_amount),
        round_off_amount=Decimal(invoice.round_off_amount),
        total_amount=Decimal(invoice.total_amount),
        rounding_tolerance=tolerance,
        line_items=resolved_items,
        supplier_gstin=invoice.supplier_gstin_snapshot,
        buyer_gstin=invoice.buyer_gstin_snapshot,
        place_of_supply_code=invoice.place_of_supply_code,
        is_reverse_charge=invoice.is_reverse_charge,
    )
    _apply_reconciliation_to_invoice(invoice, recon)

    enable_dups = (
        ws_settings.enable_duplicate_warnings if ws_settings is not None else True
    )
    dup_matches, duplicate_warning = detect_advisory_duplicates(
        db,
        workspace_id=workspace.id,
        enable_duplicate_warnings=enable_dups,
        exclude_invoice_id=invoice.id,
        supplier_id=invoice.supplier_id,
        supplier_gstin=invoice.supplier_gstin_snapshot,
        supplier_name=invoice.supplier_name_snapshot,
        normalized_invoice_number=invoice.normalized_invoice_number,
        invoice_date=invoice.invoice_date,
        total_amount=Decimal(invoice.total_amount),
    )
    invoice.duplicate_warning = duplicate_warning

    sorted_changed_fields = sorted(set(changed_fields))
    db.add(
        ReviewAction(
            workspace_id=workspace.id,
            invoice_id=invoice.id,
            actor_user_id=actor.id,
            action_type="SAVE_EDITS",
            previous_status=invoice.status,
            new_status=invoice.status,
            variance_acknowledged=False,
            variance_amount_at_action=quantize_money(Decimal(invoice.variance_amount)),
            comment=(
                f"Saved edits to: {', '.join(sorted_changed_fields)}"
                if sorted_changed_fields
                else "Saved invoice review update."
            ),
            field_changes={"updatedFields": sorted_changed_fields},
        )
    )
    db.flush()

    record_audit_event(
        db,
        organization_id=workspace.organization_id,
        workspace_id=workspace.id,
        actor_user=actor,
        event_type="invoice.updated",
        entity_type="invoice",
        entity_id=invoice.id,
        summary=f"Updated invoice '{invoice.invoice_number}' ({invoice.status}).",
        tone="warning"
        if (
            recon.reconciliation_status == "VARIANCE_DETECTED"
            or recon.line_item_reconciliation_status == "VARIANCE_WARNING"
            or duplicate_warning is not None
        )
        else "neutral",
        metadata={
            "invoiceId": str(invoice.id),
            "updatedFields": sorted_changed_fields,
            "status": invoice.status,
            "reconciliationStatus": invoice.reconciliation_status,
            "lineItemReconciliationStatus": invoice.line_item_reconciliation_status,
            "hasDuplicateWarning": duplicate_warning is not None,
            "duplicateMatchCount": len(dup_matches),
        },
        ip_address=ip_address,
    )
    db.commit()
    db.expire(invoice)

    return _load_active_invoice_detail(
        db,
        workspace_id=workspace.id,
        invoice_id=invoice.id,
        ws_settings=ws_settings,
    )


def soft_delete_invoice(
    db: Session,
    *,
    workspace: Workspace,
    invoice_id: uuid.UUID,
    actor: User,
    deletion_reason: str | None,
    ip_address: str | None,
) -> None:
    """
    Soft-delete an unverified (PENDING_REVIEW or FLAGGED) invoice while preserving
    line items, field verifications, review flags, review actions, and audit history.
    Never allows deleting VERIFIED invoices.
    """
    invoice = db.scalar(
        select(Invoice)
        .where(
            Invoice.id == invoice_id,
            Invoice.workspace_id == workspace.id,
            Invoice.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if invoice is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="INVOICE_NOT_FOUND",
            message="Invoice not found.",
        )

    if invoice.status == "VERIFIED":
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="CANNOT_DELETE_VERIFIED_INVOICE",
            message="Verified invoices cannot be deleted.",
        )

    invoice.deleted_at = utc_now()
    invoice.deleted_by_user_id = actor.id
    invoice.deletion_reason = deletion_reason
    db.flush()

    record_audit_event(
        db,
        organization_id=workspace.organization_id,
        workspace_id=workspace.id,
        actor_user=actor,
        event_type="invoice.soft_deleted",
        entity_type="invoice",
        entity_id=invoice.id,
        summary=f"Soft-deleted unverified invoice '{invoice.invoice_number}' ({invoice.status}).",
        tone="warning",
        metadata={
            "invoiceId": str(invoice.id),
            "previousStatus": invoice.status,
            "hasDeletionReason": bool(deletion_reason),
        },
        ip_address=ip_address,
    )
    db.commit()
