from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from fastapi import status
from pydantic.alias_generators import to_camel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import AppError
from app.models.accounting import (
    Invoice,
    InvoiceFieldVerification,
    InvoiceLineItem,
)
from app.models.review import AuditEvent, InvoiceReviewFlag, ReviewAction
from app.models.tenancy import User, Workspace, utc_now
from app.schemas.invoices import InvoiceStatus
from app.schemas.review import (
    FlagInvoiceRequest,
    ReopenInvoiceRequest,
    ResolveFlagRequest,
    ReviewHistoryOrder,
    VerifyInvoiceRequest,
)
from app.services.audit_service import record_audit_event
from app.services.invoice_service import (
    InvoiceDetailRecord,
    get_workspace_settings,
    is_draft_placeholder_number,
    is_placeholder_supplier_name,
    load_active_invoice_detail,
)
from app.services.reconciliation_service import (
    DEFAULT_ROUNDING_TOLERANCE,
    ZERO,
    quantize_money,
    reconcile_invoice,
    resolve_existing_line_items,
)


@dataclass(frozen=True)
class FlagResolutionResult:
    flag: InvoiceReviewFlag
    invoice_id: uuid.UUID
    invoice_status: InvoiceStatus
    open_flag_count: int


@dataclass(frozen=True)
class ReviewHistoryResult:
    invoice_id: uuid.UUID
    status: InvoiceStatus
    actions: list[ReviewAction]
    flags: list[InvoiceReviewFlag]
    audit_events: list[AuditEvent]
    total_actions: int
    total_flags: int
    total_audit_events: int
    page: int
    page_size: int


def _lock_active_invoice(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    invoice_id: uuid.UUID,
) -> Invoice:
    invoice = db.scalar(
        select(Invoice)
        .where(
            Invoice.id == invoice_id,
            Invoice.workspace_id == workspace_id,
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
    return invoice


def _validate_mandatory_fields_for_verification(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    invoice: Invoice,
) -> None:
    missing_fields: list[str] = []
    if (
        not invoice.supplier_name_snapshot.strip()
        or is_placeholder_supplier_name(invoice.supplier_name_snapshot)
    ):
        missing_fields.append("supplierName")
    if (
        not invoice.invoice_number.strip()
        or is_draft_placeholder_number(invoice.normalized_invoice_number)
    ):
        missing_fields.append("invoiceNumber")
    if invoice.invoice_date is None:
        missing_fields.append("invoiceDate")
    if (
        invoice.reconciliation_status == "PENDING_INPUT"
        and quantize_money(Decimal(invoice.total_amount)) == ZERO
    ):
        missing_fields.append("totalAmount")

    tracked_fvs = list(
        db.scalars(
            select(InvoiceFieldVerification).where(
                InvoiceFieldVerification.workspace_id == workspace_id,
                InvoiceFieldVerification.invoice_id == invoice.id,
            )
        )
    )
    unverified_fields = sorted(
        to_camel(fv.field_key) for fv in tracked_fvs if fv.status != "VERIFIED"
    )

    if missing_fields or unverified_fields:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="MISSING_REQUIRED_FIELD_VERIFICATION",
            message=(
                "All mandatory invoice fields and tracked field verifications "
                "must be completed and VERIFIED before verifying this invoice."
            ),
            details={
                "missingFields": missing_fields,
                "unverifiedFields": unverified_fields,
            },
        )


def verify_invoice(
    db: Session,
    *,
    workspace: Workspace,
    invoice_id: uuid.UUID,
    actor: User,
    payload: VerifyInvoiceRequest,
    ip_address: str | None,
) -> InvoiceDetailRecord:
    """Perform mandatory human verification sign-off under a row lock."""
    invoice = _lock_active_invoice(
        db, workspace_id=workspace.id, invoice_id=invoice_id
    )
    ws_settings = get_workspace_settings(db, workspace.id)
    if ws_settings is not None and not ws_settings.require_human_review:
        raise AppError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="HUMAN_REVIEW_CANNOT_BE_DISABLED",
            message="Mandatory human review is enforced for all workspaces.",
        )

    if invoice.status == "VERIFIED":
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="INVOICE_ALREADY_VERIFIED",
            message="Invoice has already been verified.",
        )

    open_flags = list(
        db.scalars(
            select(InvoiceReviewFlag)
            .where(
                InvoiceReviewFlag.workspace_id == workspace.id,
                InvoiceReviewFlag.invoice_id == invoice.id,
                InvoiceReviewFlag.status == "OPEN",
            )
            .order_by(InvoiceReviewFlag.created_at.asc(), InvoiceReviewFlag.id.asc())
            .with_for_update()
        )
    )

    if (
        payload.flag_resolution_note is not None
        and not payload.flag_resolution_note.strip()
    ):
        raise AppError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="INVALID_FLAG_RESOLUTION",
            message="flagResolutionNote cannot be blank when provided.",
        )

    resolved_flag_note = (
        payload.flag_resolution_note or payload.confirmation_note
    ).strip()
    if open_flags:
        if not payload.resolve_open_flags:
            raise AppError(
                status_code=status.HTTP_409_CONFLICT,
                code="UNRESOLVED_REVIEW_FLAGS",
                message=(
                    "Open review flags must be resolved before verifying this invoice, "
                    "or pass resolveOpenFlags=true with a resolution note."
                ),
                details={
                    "openFlagCount": len(open_flags),
                    "openFlagIds": [str(flag.id) for flag in open_flags],
                },
            )
        if not resolved_flag_note:
            raise AppError(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="INVALID_FLAG_RESOLUTION",
                message=(
                    "A non-blank flagResolutionNote or confirmationNote is required "
                    "when resolveOpenFlags is true."
                ),
            )

    if payload.field_verifications is not None:
        if any(fv.status != "VERIFIED" for fv in payload.field_verifications):
            raise AppError(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="INVALID_FIELD_VERIFICATION_STATUS",
                message=(
                    "All fieldVerifications submitted during final verification "
                    "must have status VERIFIED."
                ),
            )
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
                        status="VERIFIED",
                        evidence_note=fv_in.evidence_note,
                        source_page=fv_in.source_page,
                        bounding_box=fv_in.bounding_box,
                        confidence_score=fv_in.confidence_score,
                        verified_by_user_id=actor.id,
                    )
                )
            else:
                target.status = "VERIFIED"
                target.evidence_note = fv_in.evidence_note
                target.source_page = fv_in.source_page
                target.bounding_box = fv_in.bounding_box
                target.confidence_score = fv_in.confidence_score
                target.verified_by_user_id = actor.id
        db.flush()

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
    invoice.computed_expected_total = recon.computed_expected_total
    invoice.variance_amount = recon.variance_amount
    invoice.reconciliation_status = recon.reconciliation_status
    invoice.line_items_taxable_sum = recon.line_items_taxable_sum
    invoice.line_item_variance_amount = recon.line_item_variance_amount
    invoice.line_item_reconciliation_status = recon.line_item_reconciliation_status
    invoice.line_item_warning = recon.line_item_warning

    _validate_mandatory_fields_for_verification(
        db, workspace_id=workspace.id, invoice=invoice
    )

    has_header_variance = abs(recon.variance_amount) > tolerance
    has_line_item_variance = recon.line_item_reconciliation_status == "VARIANCE_WARNING"
    has_variance = has_header_variance or has_line_item_variance

    if has_variance and (
        not payload.confirm_variance_acknowledgment or not payload.confirmation_note
    ):
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="VARIANCE_ACKNOWLEDGMENT_REQUIRED",
            message=(
                "Invoice or line-item reconciliation variance requires explicit "
                "human confirmation and a confirmation note before verification."
            ),
            details={
                "varianceAmount": f"{recon.variance_amount:.2f}",
                "computedExpectedTotal": f"{recon.computed_expected_total:.2f}",
                "declaredTotal": f"{recon.declared_total:.2f}",
                "roundingTolerance": f"{tolerance:.2f}",
                "lineItemReconciliationStatus": recon.line_item_reconciliation_status,
                "lineItemVarianceAmount": (
                    f"{recon.line_item_variance_amount:.2f}"
                    if recon.line_item_variance_amount is not None
                    else "0.00"
                ),
            },
        )

    now = utc_now()
    previous_status = invoice.status

    resolved_flag_ids: list[str] = []
    for flag in open_flags:
        flag.status = "RESOLVED"
        flag.resolved_by_user_id = actor.id
        flag.resolved_at = now
        flag.resolution_note = resolved_flag_note
        resolved_flag_ids.append(str(flag.id))
        db.add(
            ReviewAction(
                workspace_id=workspace.id,
                invoice_id=invoice.id,
                actor_user_id=actor.id,
                action_type="RESOLVE_FLAG",
                previous_status=previous_status,
                new_status=previous_status,
                variance_acknowledged=False,
                variance_amount_at_action=quantize_money(recon.variance_amount),
                comment=resolved_flag_note,
                field_changes={
                    "flagId": str(flag.id),
                    "flagCategory": flag.flag_category,
                    "resolutionStatus": "RESOLVED",
                    "resolvedDuringVerification": True,
                },
                created_at=now,
            )
        )

    invoice.status = "VERIFIED"
    invoice.verified_by_user_id = actor.id
    invoice.verified_at = now
    db.flush()

    action_type = "VERIFY_WITH_VARIANCE" if has_variance else "MARK_VERIFIED"
    variance_acknowledged = bool(has_variance or payload.confirm_variance_acknowledgment)
    action_comment = (
        payload.confirmation_note
        if payload.confirmation_note
        else "Verified invoice after human review."
    )
    db.add(
        ReviewAction(
            workspace_id=workspace.id,
            invoice_id=invoice.id,
            actor_user_id=actor.id,
            action_type=action_type,
            previous_status=previous_status,
            new_status="VERIFIED",
            variance_acknowledged=variance_acknowledged,
            variance_amount_at_action=quantize_money(recon.variance_amount),
            comment=action_comment,
            field_changes={
                "roundingTolerance": f"{tolerance:.2f}",
                "reconciliationStatus": recon.reconciliation_status,
                "lineItemReconciliationStatus": recon.line_item_reconciliation_status,
                "resolvedFlagIds": resolved_flag_ids,
            },
            created_at=now + timedelta(microseconds=1),
        )
    )
    db.flush()

    summary = (
        f"Verified invoice '{invoice.invoice_number}' after explicit human "
        f"confirmation of variance ({recon.variance_amount:.2f})."
        if has_variance
        else f"Verified invoice '{invoice.invoice_number}' after human review."
    )
    record_audit_event(
        db,
        organization_id=workspace.organization_id,
        workspace_id=workspace.id,
        actor_user=actor,
        event_type="invoice.verified",
        entity_type="invoice",
        entity_id=invoice.id,
        summary=summary,
        tone="warning" if has_variance else "success",
        metadata={
            "invoiceId": str(invoice.id),
            "previousStatus": previous_status,
            "newStatus": "VERIFIED",
            "actionType": action_type,
            "varianceAcknowledged": variance_acknowledged,
            "varianceAmount": f"{recon.variance_amount:.2f}",
            "lineItemReconciliationStatus": recon.line_item_reconciliation_status,
            "resolvedFlagCount": len(resolved_flag_ids),
        },
        ip_address=ip_address,
    )
    db.commit()
    db.expire(invoice)

    return load_active_invoice_detail(
        db,
        workspace_id=workspace.id,
        invoice_id=invoice.id,
        ws_settings=ws_settings,
    )


def flag_invoice(
    db: Session,
    *,
    workspace: Workspace,
    invoice_id: uuid.UUID,
    actor: User,
    payload: FlagInvoiceRequest,
    ip_address: str | None,
) -> InvoiceDetailRecord:
    """Flag an active invoice for secondary human review and record immutable logs."""
    invoice = _lock_active_invoice(
        db, workspace_id=workspace.id, invoice_id=invoice_id
    )
    previous_status = invoice.status

    flag = InvoiceReviewFlag(
        workspace_id=workspace.id,
        invoice_id=invoice.id,
        flag_category=payload.flag_category,
        reason_text=payload.reason_text,
        status="OPEN",
        created_by_user_id=actor.id,
    )
    db.add(flag)

    if payload.field_key is not None:
        existing_fv = db.scalar(
            select(InvoiceFieldVerification).where(
                InvoiceFieldVerification.workspace_id == workspace.id,
                InvoiceFieldVerification.invoice_id == invoice.id,
                InvoiceFieldVerification.field_key == payload.field_key,
            )
        )
        if existing_fv is None:
            db.add(
                InvoiceFieldVerification(
                    workspace_id=workspace.id,
                    invoice_id=invoice.id,
                    field_key=payload.field_key,
                    status="FLAGGED",
                    evidence_note=payload.reason_text,
                    verified_by_user_id=None,
                )
            )
        else:
            existing_fv.status = "FLAGGED"
            existing_fv.evidence_note = payload.reason_text
            existing_fv.verified_by_user_id = None

    invoice.status = "FLAGGED"
    invoice.verified_by_user_id = None
    invoice.verified_at = None
    db.flush()

    field_changes: dict[str, object] = {
        "flagId": str(flag.id),
        "flagCategory": flag.flag_category,
    }
    if payload.field_key is not None:
        field_changes["fieldKey"] = to_camel(payload.field_key)

    db.add(
        ReviewAction(
            workspace_id=workspace.id,
            invoice_id=invoice.id,
            actor_user_id=actor.id,
            action_type="FLAG_INVOICE",
            previous_status=previous_status,
            new_status="FLAGGED",
            variance_acknowledged=False,
            variance_amount_at_action=quantize_money(Decimal(invoice.variance_amount)),
            comment=payload.reason_text,
            field_changes=field_changes,
        )
    )
    db.flush()

    record_audit_event(
        db,
        organization_id=workspace.organization_id,
        workspace_id=workspace.id,
        actor_user=actor,
        event_type="invoice.flagged",
        entity_type="invoice",
        entity_id=invoice.id,
        summary=(
            f"Flagged invoice '{invoice.invoice_number}' "
            f"({payload.flag_category}): {payload.reason_text}"
        ),
        tone="warning",
        metadata={
            "invoiceId": str(invoice.id),
            "flagId": str(flag.id),
            "flagCategory": payload.flag_category,
            "previousStatus": previous_status,
            "newStatus": "FLAGGED",
            **(
                {"fieldKey": to_camel(payload.field_key)}
                if payload.field_key is not None
                else {}
            ),
        },
        ip_address=ip_address,
    )
    db.commit()
    db.expire(invoice)

    return load_active_invoice_detail(
        db,
        workspace_id=workspace.id,
        invoice_id=invoice.id,
    )


def resolve_review_flag(
    db: Session,
    *,
    workspace: Workspace,
    flag_id: uuid.UUID,
    actor: User,
    payload: ResolveFlagRequest,
    ip_address: str | None,
) -> FlagResolutionResult:
    """
    Resolve or dismiss an open exception flag in the workspace.

    Acquires locks strictly in canonical Invoice -> InvoiceReviewFlag order
    to prevent cross-endpoint PostgreSQL deadlocks.
    """
    target_invoice_id = db.scalar(
        select(InvoiceReviewFlag.invoice_id).where(
            InvoiceReviewFlag.id == flag_id,
            InvoiceReviewFlag.workspace_id == workspace.id,
        )
    )
    if target_invoice_id is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="FLAG_NOT_FOUND",
            message="Review flag not found.",
        )

    invoice = _lock_active_invoice(
        db, workspace_id=workspace.id, invoice_id=target_invoice_id
    )
    flag = db.scalar(
        select(InvoiceReviewFlag)
        .where(
            InvoiceReviewFlag.id == flag_id,
            InvoiceReviewFlag.workspace_id == workspace.id,
            InvoiceReviewFlag.invoice_id == invoice.id,
        )
        .with_for_update()
    )
    if flag is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="FLAG_NOT_FOUND",
            message="Review flag not found.",
        )

    if flag.status != "OPEN":
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="FLAG_ALREADY_RESOLVED",
            message=f"Review flag has already been marked {flag.status}.",
        )

    now = utc_now()
    flag.status = payload.resolution_status
    flag.resolved_by_user_id = actor.id
    flag.resolved_at = now
    flag.resolution_note = payload.resolution_note
    db.flush()

    remaining_open = int(
        db.scalar(
            select(func.count(InvoiceReviewFlag.id)).where(
                InvoiceReviewFlag.workspace_id == workspace.id,
                InvoiceReviewFlag.invoice_id == invoice.id,
                InvoiceReviewFlag.status == "OPEN",
            )
        )
        or 0
    )

    previous_status = invoice.status
    new_status = previous_status
    if (
        invoice.status == "FLAGGED"
        and remaining_open == 0
        and payload.reopen_to_pending
    ):
        invoice.status = "PENDING_REVIEW"
        new_status = "PENDING_REVIEW"

    db.flush()

    db.add(
        ReviewAction(
            workspace_id=workspace.id,
            invoice_id=invoice.id,
            actor_user_id=actor.id,
            action_type="RESOLVE_FLAG",
            previous_status=previous_status,
            new_status=new_status,
            variance_acknowledged=False,
            variance_amount_at_action=quantize_money(Decimal(invoice.variance_amount)),
            comment=payload.resolution_note,
            field_changes={
                "flagId": str(flag.id),
                "flagCategory": flag.flag_category,
                "resolutionStatus": flag.status,
                "remainingOpenFlags": remaining_open,
            },
        )
    )
    db.flush()

    record_audit_event(
        db,
        organization_id=workspace.organization_id,
        workspace_id=workspace.id,
        actor_user=actor,
        event_type="invoice.flag_resolved",
        entity_type="invoice",
        entity_id=invoice.id,
        summary=(
            f"Marked review flag {flag.flag_category} on '{invoice.invoice_number}' "
            f"as {flag.status}: {payload.resolution_note}"
        ),
        tone="neutral" if remaining_open == 0 else "warning",
        metadata={
            "invoiceId": str(invoice.id),
            "flagId": str(flag.id),
            "flagCategory": flag.flag_category,
            "resolutionStatus": flag.status,
            "previousStatus": previous_status,
            "newStatus": new_status,
            "remainingOpenFlags": remaining_open,
        },
        ip_address=ip_address,
    )
    db.commit()

    refreshed_flag = db.scalar(
        select(InvoiceReviewFlag)
        .options(
            joinedload(InvoiceReviewFlag.created_by_user),
            joinedload(InvoiceReviewFlag.resolved_by_user),
        )
        .where(
            InvoiceReviewFlag.id == flag.id,
            InvoiceReviewFlag.workspace_id == workspace.id,
        )
    )
    assert refreshed_flag is not None
    return FlagResolutionResult(
        flag=refreshed_flag,
        invoice_id=invoice.id,
        invoice_status=new_status,  # type: ignore[arg-type]
        open_flag_count=remaining_open,
    )


def reopen_invoice(
    db: Session,
    *,
    workspace: Workspace,
    invoice_id: uuid.UUID,
    actor: User,
    payload: ReopenInvoiceRequest,
    ip_address: str | None,
) -> InvoiceDetailRecord:
    """
    Reopen a VERIFIED (or flag-cleared FLAGGED) invoice back to PENDING_REVIEW
    while preserving all historical review actions, flags, and audit events.
    """
    invoice = _lock_active_invoice(
        db, workspace_id=workspace.id, invoice_id=invoice_id
    )
    if invoice.status == "PENDING_REVIEW":
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="INVALID_INVOICE_STATE_TRANSITION",
            message="Invoice is already in PENDING_REVIEW status.",
        )

    open_flag_count = int(
        db.scalar(
            select(func.count(InvoiceReviewFlag.id)).where(
                InvoiceReviewFlag.workspace_id == workspace.id,
                InvoiceReviewFlag.invoice_id == invoice.id,
                InvoiceReviewFlag.status == "OPEN",
            )
        )
        or 0
    )
    if invoice.status == "FLAGGED" and open_flag_count > 0:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="UNRESOLVED_REVIEW_FLAGS",
            message=(
                "Cannot reopen a flagged invoice while open review flags remain; "
                "resolve or dismiss open flags instead."
            ),
            details={"openFlagCount": open_flag_count},
        )

    previous_status = invoice.status
    previous_verified_by = (
        str(invoice.verified_by_user_id) if invoice.verified_by_user_id else None
    )
    previous_verified_at = (
        invoice.verified_at.isoformat() if invoice.verified_at is not None else None
    )

    invoice.status = "PENDING_REVIEW"
    invoice.verified_by_user_id = None
    invoice.verified_at = None
    db.flush()

    db.add(
        ReviewAction(
            workspace_id=workspace.id,
            invoice_id=invoice.id,
            actor_user_id=actor.id,
            action_type="REOPEN_PENDING",
            previous_status=previous_status,
            new_status="PENDING_REVIEW",
            variance_acknowledged=False,
            variance_amount_at_action=quantize_money(Decimal(invoice.variance_amount)),
            comment=payload.reason,
            field_changes={
                "previousVerifiedByUserId": previous_verified_by,
                "previousVerifiedAt": previous_verified_at,
            },
        )
    )
    db.flush()

    record_audit_event(
        db,
        organization_id=workspace.organization_id,
        workspace_id=workspace.id,
        actor_user=actor,
        event_type="invoice.reopened",
        entity_type="invoice",
        entity_id=invoice.id,
        summary=(
            f"Reopened invoice '{invoice.invoice_number}' from {previous_status} "
            f"to PENDING_REVIEW: {payload.reason}"
        ),
        tone="warning",
        metadata={
            "invoiceId": str(invoice.id),
            "previousStatus": previous_status,
            "newStatus": "PENDING_REVIEW",
            "reason": payload.reason,
        },
        ip_address=ip_address,
    )
    db.commit()
    db.expire(invoice)

    return load_active_invoice_detail(
        db,
        workspace_id=workspace.id,
        invoice_id=invoice.id,
    )


def get_invoice_review_history(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    invoice_id: uuid.UUID,
    order: ReviewHistoryOrder = "asc",
    page: int = 1,
    page_size: int = 50,
) -> ReviewHistoryResult:
    """
    Return immutable review actions, flags, and sanitized invoice audit events.

    Remains readable for soft-deleted invoices inside the same workspace for
    compliance traceability, while rejecting foreign-workspace UUIDs with 404.
    """
    invoice_row = db.execute(
        select(Invoice.id, Invoice.status).where(
            Invoice.id == invoice_id,
            Invoice.workspace_id == workspace_id,
        )
    ).first()
    if invoice_row is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="INVOICE_NOT_FOUND",
            message="Invoice not found.",
        )

    total_actions = int(
        db.scalar(
            select(func.count(ReviewAction.id)).where(
                ReviewAction.workspace_id == workspace_id,
                ReviewAction.invoice_id == invoice_id,
            )
        )
        or 0
    )
    action_ordering = (
        (ReviewAction.created_at.asc(), ReviewAction.id.asc())
        if order == "asc"
        else (ReviewAction.created_at.desc(), ReviewAction.id.desc())
    )
    actions = list(
        db.scalars(
            select(ReviewAction)
            .options(joinedload(ReviewAction.actor_user))
            .where(
                ReviewAction.workspace_id == workspace_id,
                ReviewAction.invoice_id == invoice_id,
            )
            .order_by(*action_ordering)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )

    flag_ordering = (
        (InvoiceReviewFlag.created_at.asc(), InvoiceReviewFlag.id.asc())
        if order == "asc"
        else (InvoiceReviewFlag.created_at.desc(), InvoiceReviewFlag.id.desc())
    )
    flags = list(
        db.scalars(
            select(InvoiceReviewFlag)
            .options(
                joinedload(InvoiceReviewFlag.created_by_user),
                joinedload(InvoiceReviewFlag.resolved_by_user),
            )
            .where(
                InvoiceReviewFlag.workspace_id == workspace_id,
                InvoiceReviewFlag.invoice_id == invoice_id,
            )
            .order_by(*flag_ordering)
        )
    )

    audit_conditions = (
        AuditEvent.workspace_id == workspace_id,
        AuditEvent.entity_type == "invoice",
        AuditEvent.entity_id == invoice_id,
    )
    total_audit_events = int(
        db.scalar(select(func.count(AuditEvent.id)).where(*audit_conditions)) or 0
    )
    audit_ordering = (
        (AuditEvent.created_at.asc(), AuditEvent.id.asc())
        if order == "asc"
        else (AuditEvent.created_at.desc(), AuditEvent.id.desc())
    )
    audit_events = list(
        db.scalars(
            select(AuditEvent)
            .where(*audit_conditions)
            .order_by(*audit_ordering)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )

    return ReviewHistoryResult(
        invoice_id=invoice_row[0],
        status=invoice_row[1],
        actions=actions,
        flags=flags,
        audit_events=audit_events,
        total_actions=total_actions,
        total_flags=len(flags),
        total_audit_events=total_audit_events,
        page=page,
        page_size=page_size,
    )
