from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from fastapi import status
from pydantic.alias_generators import to_camel
from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import Subquery

from app.core.errors import AppError
from app.models.accounting import Invoice, Supplier
from app.models.tenancy import User, Workspace
from app.schemas.suppliers import (
    SupplierCreateRequest,
    SupplierStatus,
    SupplierUpdateRequest,
    normalize_supplier_name,
)
from app.services.audit_service import record_audit_event


@dataclass(frozen=True)
class SupplierWithStats:
    supplier: Supplier
    total_invoices: int
    total_value: Decimal
    last_invoice_date: date | None


def _get_constraint_name(exc: IntegrityError) -> str | None:
    return getattr(getattr(exc.orig, "diag", None), "constraint_name", None)


def _raise_supplier_conflict(exc: IntegrityError) -> None:
    constraint_name = _get_constraint_name(exc)
    orig_text = str(exc.orig) if exc.orig is not None else ""

    if (
        constraint_name == "uq_suppliers_workspace_id_normalized_name"
        or "uq_suppliers_workspace_id_normalized_name" in orig_text
    ):
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="SUPPLIER_NAME_EXISTS",
            message="A supplier with this normalized name already exists in the workspace.",
        ) from exc

    if (
        constraint_name == "uq_suppliers_workspace_gstin"
        or "uq_suppliers_workspace_gstin" in orig_text
    ):
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="SUPPLIER_GSTIN_EXISTS",
            message="A supplier with this GSTIN already exists in the workspace.",
        ) from exc

    raise exc


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _build_invoice_aggregate_subquery(workspace_id: uuid.UUID) -> Subquery:
    return (
        select(
            Invoice.supplier_id.label("supplier_id"),
            func.count(Invoice.id).label("total_invoices"),
            func.coalesce(func.sum(Invoice.total_amount), Decimal("0.00")).label(
                "total_value"
            ),
            func.max(Invoice.invoice_date).label("last_invoice_date"),
        )
        .where(
            Invoice.workspace_id == workspace_id,
            Invoice.supplier_id.is_not(None),
            Invoice.deleted_at.is_(None),
        )
        .group_by(Invoice.supplier_id)
        .subquery()
    )


def _select_suppliers_with_stats(
    workspace_id: uuid.UUID,
) -> Select[tuple[Supplier, int, Decimal, date | None]]:
    agg = _build_invoice_aggregate_subquery(workspace_id)
    return select(
        Supplier,
        func.coalesce(agg.c.total_invoices, 0).label("total_invoices"),
        func.coalesce(agg.c.total_value, Decimal("0.00")).label("total_value"),
        agg.c.last_invoice_date.label("last_invoice_date"),
    ).outerjoin(agg, agg.c.supplier_id == Supplier.id)


def _to_supplier_with_stats(
    row: tuple[Supplier, int, Decimal, date | None],
) -> SupplierWithStats:
    supplier, total_invoices, total_value, last_invoice_date = row
    quantized_total = Decimal(str(total_value or "0.00")).quantize(Decimal("0.01"))
    return SupplierWithStats(
        supplier=supplier,
        total_invoices=int(total_invoices or 0),
        total_value=quantized_total,
        last_invoice_date=last_invoice_date,
    )


def list_suppliers(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    search: str | None = None,
    status_filter: SupplierStatus | None = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[SupplierWithStats], int]:
    """List workspace-scoped suppliers with SQL-aggregated invoice statistics."""
    conditions = [Supplier.workspace_id == workspace_id]

    if status_filter is not None:
        conditions.append(Supplier.status == status_filter)

    cleaned_search = search.strip() if search is not None else ""
    if cleaned_search:
        pattern = f"%{_escape_like(cleaned_search)}%"
        conditions.append(
            or_(
                Supplier.name.ilike(pattern, escape="\\"),
                Supplier.normalized_name.ilike(pattern, escape="\\"),
                func.coalesce(Supplier.gstin, "").ilike(pattern, escape="\\"),
                func.coalesce(Supplier.pan, "").ilike(pattern, escape="\\"),
                Supplier.category.ilike(pattern, escape="\\"),
                func.coalesce(Supplier.state_name, "").ilike(pattern, escape="\\"),
                func.coalesce(Supplier.email, "").ilike(pattern, escape="\\"),
            )
        )

    total = db.scalar(select(func.count(Supplier.id)).where(*conditions)) or 0

    stmt = (
        _select_suppliers_with_stats(workspace_id)
        .where(*conditions)
        .order_by(Supplier.name.asc(), Supplier.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = db.execute(stmt).all()
    return [_to_supplier_with_stats((r[0], r[1], r[2], r[3])) for r in rows], int(total)


def get_supplier_detail(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    supplier_id: uuid.UUID,
) -> SupplierWithStats:
    """Fetch a single workspace-scoped supplier with SQL-aggregated invoice statistics."""
    row = db.execute(
        _select_suppliers_with_stats(workspace_id).where(
            Supplier.workspace_id == workspace_id,
            Supplier.id == supplier_id,
        )
    ).first()
    if row is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="SUPPLIER_NOT_FOUND",
            message="Supplier not found.",
        )
    return _to_supplier_with_stats((row[0], row[1], row[2], row[3]))


def create_supplier(
    db: Session,
    *,
    workspace: Workspace,
    actor: User,
    payload: SupplierCreateRequest,
    ip_address: str | None,
) -> Supplier:
    """Create a workspace-scoped supplier with normalized-name and GSTIN uniqueness enforcement."""
    normalized_name = normalize_supplier_name(payload.name)

    existing_name_id = db.scalar(
        select(Supplier.id).where(
            Supplier.workspace_id == workspace.id,
            Supplier.normalized_name == normalized_name,
        )
    )
    if existing_name_id is not None:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="SUPPLIER_NAME_EXISTS",
            message="A supplier with this normalized name already exists in the workspace.",
        )

    if payload.gstin is not None:
        existing_gstin_id = db.scalar(
            select(Supplier.id).where(
                Supplier.workspace_id == workspace.id,
                Supplier.gstin == payload.gstin,
            )
        )
        if existing_gstin_id is not None:
            raise AppError(
                status_code=status.HTTP_409_CONFLICT,
                code="SUPPLIER_GSTIN_EXISTS",
                message="A supplier with this GSTIN already exists in the workspace.",
            )

    supplier = Supplier(
        workspace_id=workspace.id,
        name=payload.name,
        normalized_name=normalized_name,
        gstin=payload.gstin,
        pan=payload.pan,
        state_code=payload.state_code,
        state_name=payload.state_name,
        category=payload.category,
        email=payload.email,
        status=payload.status,
    )

    try:
        db.add(supplier)
        db.flush()

        record_audit_event(
            db,
            organization_id=workspace.organization_id,
            workspace_id=workspace.id,
            actor_user=actor,
            event_type="supplier.created",
            entity_type="supplier",
            entity_id=supplier.id,
            summary=f"Created supplier record '{supplier.name}' ({supplier.status}).",
            tone="success",
            metadata={
                "supplierId": str(supplier.id),
                "status": supplier.status,
                "hasGstin": supplier.gstin is not None,
            },
            ip_address=ip_address,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_supplier_conflict(exc)

    db.refresh(supplier)
    return supplier


def update_supplier(
    db: Session,
    *,
    workspace: Workspace,
    supplier_id: uuid.UUID,
    actor: User,
    payload: SupplierUpdateRequest,
    ip_address: str | None,
) -> Supplier:
    """Update mutable workspace-scoped supplier fields and emit a compliance audit event."""
    supplier = db.scalar(
        select(Supplier)
        .where(
            Supplier.id == supplier_id,
            Supplier.workspace_id == workspace.id,
        )
        .with_for_update()
    )
    if supplier is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="SUPPLIER_NOT_FOUND",
            message="Supplier not found.",
        )

    updates = payload.model_dump(exclude_unset=True)
    new_normalized_name: str | None = None
    if "name" in updates:
        new_name = updates["name"]
        assert isinstance(new_name, str)
        new_normalized_name = normalize_supplier_name(new_name)
        name_conflict = db.scalar(
            select(Supplier.id).where(
                Supplier.workspace_id == workspace.id,
                Supplier.normalized_name == new_normalized_name,
                Supplier.id != supplier.id,
            )
        )
        if name_conflict is not None:
            raise AppError(
                status_code=status.HTTP_409_CONFLICT,
                code="SUPPLIER_NAME_EXISTS",
                message="A supplier with this normalized name already exists in the workspace.",
            )

    if "gstin" in updates and updates["gstin"] is not None:
        gstin_conflict = db.scalar(
            select(Supplier.id).where(
                Supplier.workspace_id == workspace.id,
                Supplier.gstin == updates["gstin"],
                Supplier.id != supplier.id,
            )
        )
        if gstin_conflict is not None:
            raise AppError(
                status_code=status.HTTP_409_CONFLICT,
                code="SUPPLIER_GSTIN_EXISTS",
                message="A supplier with this GSTIN already exists in the workspace.",
            )

    previous_status = supplier.status
    allowed_fields = {
        "name",
        "gstin",
        "pan",
        "state_code",
        "state_name",
        "category",
        "email",
        "status",
    }
    changed_fields: list[str] = []
    for field, value in updates.items():
        if field not in allowed_fields:
            continue
        if getattr(supplier, field) != value:
            changed_fields.append(to_camel(field))
        setattr(supplier, field, value)

    if new_normalized_name is not None:
        supplier.normalized_name = new_normalized_name

    try:
        db.flush()

        audit_metadata: dict[str, object] = {
            "supplierId": str(supplier.id),
            "updatedFields": sorted(changed_fields),
            "status": supplier.status,
        }
        if previous_status != supplier.status:
            audit_metadata["previousStatus"] = previous_status

        record_audit_event(
            db,
            organization_id=workspace.organization_id,
            workspace_id=workspace.id,
            actor_user=actor,
            event_type="supplier.updated",
            entity_type="supplier",
            entity_id=supplier.id,
            summary=f"Updated supplier record '{supplier.name}' ({supplier.status}).",
            tone="warning" if supplier.status == "FLAGGED" else "neutral",
            metadata=audit_metadata,
            ip_address=ip_address,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_supplier_conflict(exc)

    db.refresh(supplier)
    return supplier
