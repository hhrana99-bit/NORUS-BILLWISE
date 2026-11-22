from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Body, Depends, Path, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.deps import (
    WorkspaceContext,
    get_client_ip,
    require_csrf,
    require_workspace_role,
)
from app.db.session import get_db
from app.schemas.invoices import (
    DuplicateMatchDto,
    InvoiceCreateRequest,
    InvoiceDeleteRequest,
    InvoiceDetailDto,
    InvoiceDocumentDescriptorDto,
    InvoiceFieldVerificationDto,
    InvoiceLineItemDto,
    InvoiceListResponse,
    InvoiceReconciliationSummaryDto,
    InvoiceSortBy,
    InvoiceStatus,
    InvoiceSummaryDto,
    InvoiceUpdateRequest,
    LineItemReconciliationStatus,
    ReconciliationDiscrepancyDto,
    ReconciliationStatus,
    SortDirection,
    TaxTypeFilter,
)
from app.services.invoice_service import (
    InvoiceDetailRecord,
    InvoiceSummaryRow,
    create_invoice,
    get_invoice_detail,
    list_invoices,
    soft_delete_invoice,
    update_invoice,
)
from app.services.reconciliation_service import (
    compute_indian_financial_year,
    determine_invoice_tax_type,
    quantize_money,
)

router = APIRouter(prefix="/workspaces/{workspaceId}/invoices", tags=["Invoices"])


def _summary_fields(row: InvoiceSummaryRow) -> dict[str, object]:
    inv = row.invoice
    cgst = quantize_money(Decimal(inv.cgst_amount))
    sgst = quantize_money(Decimal(inv.sgst_amount))
    igst = quantize_money(Decimal(inv.igst_amount))
    cess = quantize_money(Decimal(inv.cess_amount))
    tax_amount = quantize_money(cgst + sgst + igst + cess)
    return {
        "id": inv.id,
        "workspace_id": inv.workspace_id,
        "supplier_id": inv.supplier_id,
        "document_id": inv.document_id,
        "supplier_name": inv.supplier_name_snapshot,
        "supplier_gstin": inv.supplier_gstin_snapshot,
        "buyer_name": inv.buyer_name_snapshot,
        "buyer_gstin": inv.buyer_gstin_snapshot,
        "place_of_supply_code": inv.place_of_supply_code,
        "place_of_supply_name": inv.place_of_supply_name,
        "invoice_number": inv.invoice_number,
        "normalized_invoice_number": inv.normalized_invoice_number,
        "invoice_date": inv.invoice_date,
        "due_date": inv.due_date,
        "upload_date": inv.upload_date,
        "financial_year": compute_indian_financial_year(inv.invoice_date),
        "currency": inv.currency,
        "is_reverse_charge": inv.is_reverse_charge,
        "tax_type": determine_invoice_tax_type(
            cgst_amount=cgst, sgst_amount=sgst, igst_amount=igst
        ),
        "taxable_amount": quantize_money(Decimal(inv.taxable_amount)),
        "discount_amount": quantize_money(Decimal(inv.discount_amount)),
        "discount_mode": inv.discount_mode,
        "cgst_amount": cgst,
        "sgst_amount": sgst,
        "igst_amount": igst,
        "cess_amount": cess,
        "tax_amount": tax_amount,
        "freight_amount": quantize_money(Decimal(inv.freight_amount)),
        "other_charges_amount": quantize_money(Decimal(inv.other_charges_amount)),
        "round_off_amount": quantize_money(Decimal(inv.round_off_amount)),
        "total_amount": quantize_money(Decimal(inv.total_amount)),
        "computed_expected_total": quantize_money(Decimal(inv.computed_expected_total)),
        "variance_amount": quantize_money(Decimal(inv.variance_amount)),
        "reconciliation_status": inv.reconciliation_status,
        "line_items_taxable_sum": (
            quantize_money(Decimal(inv.line_items_taxable_sum))
            if inv.line_items_taxable_sum is not None
            else None
        ),
        "line_item_variance_amount": (
            quantize_money(Decimal(inv.line_item_variance_amount))
            if inv.line_item_variance_amount is not None
            else None
        ),
        "line_item_reconciliation_status": inv.line_item_reconciliation_status,
        "line_item_warning": inv.line_item_warning,
        "status": inv.status,
        "duplicate_warning": inv.duplicate_warning,
        "reviewer_note": inv.reviewer_note,
        "source_type": inv.source_type,
        "verified_by_user_id": inv.verified_by_user_id,
        "verified_at": inv.verified_at,
        "line_item_count": row.line_item_count,
        "open_flag_count": row.open_flag_count,
        "created_at": inv.created_at,
        "updated_at": inv.updated_at,
    }


def _to_invoice_summary_dto(row: InvoiceSummaryRow) -> InvoiceSummaryDto:
    return InvoiceSummaryDto(**_summary_fields(row))  # type: ignore[arg-type]


def _to_invoice_detail_dto(record: InvoiceDetailRecord) -> InvoiceDetailDto:
    inv = record.invoice
    base = _summary_fields(
        InvoiceSummaryRow(
            invoice=inv,
            line_item_count=len(inv.line_items),
            open_flag_count=record.open_flag_count,
        )
    )
    doc_dto = (
        InvoiceDocumentDescriptorDto.model_validate(inv.document)
        if inv.document is not None
        else None
    )
    line_item_dtos = [
        InvoiceLineItemDto.model_validate(li) for li in inv.line_items
    ]
    field_verif_dtos = [
        InvoiceFieldVerificationDto.model_validate(fv)
        for fv in inv.field_verifications
    ]
    recon = record.reconciliation
    recon_dto = InvoiceReconciliationSummaryDto(
        rounding_tolerance=recon.rounding_tolerance,
        computed_expected_total=recon.computed_expected_total,
        declared_total=recon.declared_total,
        variance_amount=recon.variance_amount,
        reconciliation_status=recon.reconciliation_status,
        line_items_taxable_sum=recon.line_items_taxable_sum,
        line_item_variance_amount=recon.line_item_variance_amount,
        line_item_reconciliation_status=recon.line_item_reconciliation_status,
        line_item_warning=recon.line_item_warning,
        discrepancies=[
            ReconciliationDiscrepancyDto(
                code=d.code,
                severity=d.severity,
                message=d.message,
                details=d.details,
            )
            for d in recon.discrepancies
        ],
    )
    dup_dtos = [
        DuplicateMatchDto(
            invoice_id=m.invoice_id,
            invoice_number=m.invoice_number,
            invoice_date=m.invoice_date,
            total_amount=m.total_amount,
            status=m.status,
            match_reasons=list(m.match_reasons),
        )
        for m in record.duplicate_matches
    ]
    return InvoiceDetailDto(
        **base,  # type: ignore[arg-type]
        document=doc_dto,
        line_items=line_item_dtos,
        field_verifications=field_verif_dtos,
        reconciliation=recon_dto,
        duplicate_matches=dup_dtos,
    )


@router.get(
    "",
    response_model=InvoiceListResponse,
    response_model_by_alias=True,
    summary="List active workspace invoices with search, filters, sorting, and pagination",
)
def get_invoices(
    ws_ctx: WorkspaceContext = Depends(
        require_workspace_role("WORKSPACE_ADMIN", "REVIEWER", "UPLOADER", "VIEWER")
    ),
    db: Session = Depends(get_db),
    search: str | None = Query(default=None, max_length=240),
    status_filter: InvoiceStatus | None = Query(default=None, alias="status"),
    tax_type: TaxTypeFilter | None = Query(default=None, alias="taxType"),
    supplier_id: uuid.UUID | None = Query(default=None, alias="supplierId"),
    document_id: uuid.UUID | None = Query(default=None, alias="documentId"),
    reconciliation_status: ReconciliationStatus | None = Query(
        default=None, alias="reconciliationStatus"
    ),
    line_item_reconciliation_status: LineItemReconciliationStatus | None = Query(
        default=None, alias="lineItemReconciliationStatus"
    ),
    financial_year: str | None = Query(
        default=None, alias="financialYear", max_length=16
    ),
    date_from: date | None = Query(default=None, alias="dateFrom"),
    date_to: date | None = Query(default=None, alias="dateTo"),
    sort_by: InvoiceSortBy = Query(default="uploadDate", alias="sortBy"),
    sort_dir: SortDirection = Query(default="desc", alias="sortDir"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100, alias="pageSize"),
) -> InvoiceListResponse:
    items, total = list_invoices(
        db,
        workspace_id=ws_ctx.workspace.id,
        search=search,
        status_filter=status_filter,
        tax_type=tax_type,
        supplier_id=supplier_id,
        document_id=document_id,
        reconciliation_status=reconciliation_status,
        line_item_reconciliation_status=line_item_reconciliation_status,
        financial_year=financial_year,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )
    return InvoiceListResponse(
        items=[_to_invoice_summary_dto(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=InvoiceDetailDto,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
    summary="Create a workspace invoice record in PENDING_REVIEW status (WORKSPACE_ADMIN, REVIEWER, UPLOADER)",
)
def post_invoice(
    payload: InvoiceCreateRequest,
    request: Request,
    ws_ctx: WorkspaceContext = Depends(
        require_workspace_role("WORKSPACE_ADMIN", "REVIEWER", "UPLOADER")
    ),
    db: Session = Depends(get_db),
) -> InvoiceDetailDto:
    record = create_invoice(
        db,
        workspace=ws_ctx.workspace,
        actor=ws_ctx.principal.user,
        actor_role=ws_ctx.membership.role,
        payload=payload,
        ip_address=get_client_ip(request),
    )
    return _to_invoice_detail_dto(record)


@router.get(
    "/{invoiceId}",
    response_model=InvoiceDetailDto,
    response_model_by_alias=True,
    summary="Retrieve active workspace invoice details, line items, GST reconciliation, and duplicate matches",
)
def get_invoice(
    invoice_id: uuid.UUID = Path(..., alias="invoiceId"),
    ws_ctx: WorkspaceContext = Depends(
        require_workspace_role("WORKSPACE_ADMIN", "REVIEWER", "UPLOADER", "VIEWER")
    ),
    db: Session = Depends(get_db),
) -> InvoiceDetailDto:
    record = get_invoice_detail(
        db,
        workspace_id=ws_ctx.workspace.id,
        invoice_id=invoice_id,
    )
    return _to_invoice_detail_dto(record)


@router.patch(
    "/{invoiceId}",
    response_model=InvoiceDetailDto,
    response_model_by_alias=True,
    dependencies=[Depends(require_csrf)],
    summary="Update unverified workspace invoice fields/line items and recompute GST reconciliation",
)
def patch_invoice(
    payload: InvoiceUpdateRequest,
    request: Request,
    invoice_id: uuid.UUID = Path(..., alias="invoiceId"),
    ws_ctx: WorkspaceContext = Depends(
        require_workspace_role("WORKSPACE_ADMIN", "REVIEWER", "UPLOADER")
    ),
    db: Session = Depends(get_db),
) -> InvoiceDetailDto:
    record = update_invoice(
        db,
        workspace=ws_ctx.workspace,
        invoice_id=invoice_id,
        actor=ws_ctx.principal.user,
        actor_role=ws_ctx.membership.role,
        payload=payload,
        ip_address=get_client_ip(request),
    )
    return _to_invoice_detail_dto(record)


@router.delete(
    "/{invoiceId}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    summary="Soft-delete an unverified (PENDING_REVIEW or FLAGGED) workspace invoice (WORKSPACE_ADMIN only)",
)
def delete_invoice(
    request: Request,
    invoice_id: uuid.UUID = Path(..., alias="invoiceId"),
    payload: InvoiceDeleteRequest | None = Body(default=None),
    ws_ctx: WorkspaceContext = Depends(require_workspace_role("WORKSPACE_ADMIN")),
    db: Session = Depends(get_db),
) -> Response:
    soft_delete_invoice(
        db,
        workspace=ws_ctx.workspace,
        invoice_id=invoice_id,
        actor=ws_ctx.principal.user,
        deletion_reason=payload.deletion_reason if payload is not None else None,
        ip_address=get_client_ip(request),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
