from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Body, Depends, Path, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.invoices import to_invoice_detail_dto, to_invoice_review_flag_dto
from app.core.deps import (
    WorkspaceContext,
    get_client_ip,
    require_csrf,
    require_workspace_role,
)
from app.db.session import get_db
from app.schemas.invoices import InvoiceDetailDto
from app.schemas.review import (
    FlagInvoiceRequest,
    ReopenInvoiceRequest,
    ResolveFlagRequest,
    ResolveFlagResponse,
    ReviewActionDto,
    ReviewAuditEventDto,
    ReviewHistoryOrder,
    ReviewHistoryResponse,
    VerifyInvoiceRequest,
)
from app.services.reconciliation_service import quantize_money
from app.services.review_service import (
    flag_invoice,
    get_invoice_review_history,
    reopen_invoice,
    resolve_review_flag,
    verify_invoice,
)

router = APIRouter(prefix="/workspaces/{workspaceId}", tags=["Human Review"])


@router.post(
    "/invoices/{invoiceId}/verify",
    response_model=InvoiceDetailDto,
    response_model_by_alias=True,
    dependencies=[Depends(require_csrf)],
    summary="Human sign-off verifying an invoice (WORKSPACE_ADMIN, REVIEWER only)",
)
def post_verify_invoice(
    request: Request,
    invoice_id: uuid.UUID = Path(..., alias="invoiceId"),
    payload: VerifyInvoiceRequest = Body(default_factory=VerifyInvoiceRequest),
    ws_ctx: WorkspaceContext = Depends(
        require_workspace_role("WORKSPACE_ADMIN", "REVIEWER")
    ),
    db: Session = Depends(get_db),
) -> InvoiceDetailDto:
    record = verify_invoice(
        db,
        workspace=ws_ctx.workspace,
        invoice_id=invoice_id,
        actor=ws_ctx.principal.user,
        payload=payload,
        ip_address=get_client_ip(request),
    )
    return to_invoice_detail_dto(record)


@router.post(
    "/invoices/{invoiceId}/flag",
    response_model=InvoiceDetailDto,
    response_model_by_alias=True,
    dependencies=[Depends(require_csrf)],
    summary="Flag an active invoice for secondary review (WORKSPACE_ADMIN, REVIEWER only)",
)
def post_flag_invoice(
    payload: FlagInvoiceRequest,
    request: Request,
    invoice_id: uuid.UUID = Path(..., alias="invoiceId"),
    ws_ctx: WorkspaceContext = Depends(
        require_workspace_role("WORKSPACE_ADMIN", "REVIEWER")
    ),
    db: Session = Depends(get_db),
) -> InvoiceDetailDto:
    record = flag_invoice(
        db,
        workspace=ws_ctx.workspace,
        invoice_id=invoice_id,
        actor=ws_ctx.principal.user,
        payload=payload,
        ip_address=get_client_ip(request),
    )
    return to_invoice_detail_dto(record)


@router.post(
    "/flags/{flagId}/resolve",
    response_model=ResolveFlagResponse,
    response_model_by_alias=True,
    dependencies=[Depends(require_csrf)],
    summary="Resolve or dismiss an open invoice review flag (WORKSPACE_ADMIN, REVIEWER only)",
)
def post_resolve_flag(
    payload: ResolveFlagRequest,
    request: Request,
    flag_id: uuid.UUID = Path(..., alias="flagId"),
    ws_ctx: WorkspaceContext = Depends(
        require_workspace_role("WORKSPACE_ADMIN", "REVIEWER")
    ),
    db: Session = Depends(get_db),
) -> ResolveFlagResponse:
    result = resolve_review_flag(
        db,
        workspace=ws_ctx.workspace,
        flag_id=flag_id,
        actor=ws_ctx.principal.user,
        payload=payload,
        ip_address=get_client_ip(request),
    )
    return ResolveFlagResponse(
        flag=to_invoice_review_flag_dto(result.flag),
        invoice_id=result.invoice_id,
        invoice_status=result.invoice_status,
        open_flag_count=result.open_flag_count,
    )


@router.post(
    "/invoices/{invoiceId}/reopen",
    response_model=InvoiceDetailDto,
    response_model_by_alias=True,
    dependencies=[Depends(require_csrf)],
    summary="Reopen a verified or flag-cleared invoice back to PENDING_REVIEW (WORKSPACE_ADMIN, REVIEWER only)",
)
def post_reopen_invoice(
    payload: ReopenInvoiceRequest,
    request: Request,
    invoice_id: uuid.UUID = Path(..., alias="invoiceId"),
    ws_ctx: WorkspaceContext = Depends(
        require_workspace_role("WORKSPACE_ADMIN", "REVIEWER")
    ),
    db: Session = Depends(get_db),
) -> InvoiceDetailDto:
    record = reopen_invoice(
        db,
        workspace=ws_ctx.workspace,
        invoice_id=invoice_id,
        actor=ws_ctx.principal.user,
        payload=payload,
        ip_address=get_client_ip(request),
    )
    return to_invoice_detail_dto(record)


@router.get(
    "/invoices/{invoiceId}/review-history",
    response_model=ReviewHistoryResponse,
    response_model_by_alias=True,
    summary="Retrieve chronological immutable review actions, flags, and invoice audit events",
)
def get_review_history(
    invoice_id: uuid.UUID = Path(..., alias="invoiceId"),
    order: ReviewHistoryOrder = Query(default="asc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100, alias="pageSize"),
    ws_ctx: WorkspaceContext = Depends(
        require_workspace_role("WORKSPACE_ADMIN", "REVIEWER", "UPLOADER", "VIEWER")
    ),
    db: Session = Depends(get_db),
) -> ReviewHistoryResponse:
    history = get_invoice_review_history(
        db,
        workspace_id=ws_ctx.workspace.id,
        invoice_id=invoice_id,
        order=order,
        page=page,
        page_size=page_size,
    )
    return ReviewHistoryResponse(
        invoice_id=history.invoice_id,
        status=history.status,
        actions=[
            ReviewActionDto(
                id=action.id,
                workspace_id=action.workspace_id,
                invoice_id=action.invoice_id,
                actor_user_id=action.actor_user_id,
                actor_display_name=(
                    action.actor_user.full_name
                    if action.actor_user is not None
                    else "Reviewer"
                ),
                action_type=action.action_type,
                previous_status=action.previous_status,
                new_status=action.new_status,
                variance_acknowledged=action.variance_acknowledged,
                variance_amount_at_action=(
                    quantize_money(Decimal(action.variance_amount_at_action))
                    if action.variance_amount_at_action is not None
                    else None
                ),
                comment=action.comment,
                field_changes=action.field_changes,
                created_at=action.created_at,
            )
            for action in history.actions
        ],
        flags=[to_invoice_review_flag_dto(flag) for flag in history.flags],
        audit_events=[
            ReviewAuditEventDto(
                id=evt.id,
                organization_id=evt.organization_id,
                workspace_id=evt.workspace_id,
                actor_user_id=evt.actor_user_id,
                actor_display_name=evt.actor_display_name,
                event_type=evt.event_type,
                entity_type=evt.entity_type,
                entity_id=evt.entity_id,
                summary=evt.summary,
                tone=evt.tone,  # type: ignore[arg-type]
                metadata=evt.event_metadata,
                created_at=evt.created_at,
            )
            for evt in history.audit_events
        ],
        total_actions=history.total_actions,
        total_flags=history.total_flags,
        total_audit_events=history.total_audit_events,
        page=history.page,
        page_size=history.page_size,
    )
