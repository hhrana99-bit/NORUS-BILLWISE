from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Path, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import (
    WorkspaceContext,
    get_client_ip,
    require_csrf,
    require_workspace_role,
)
from app.db.session import get_db
from app.schemas.suppliers import (
    SupplierCreateRequest,
    SupplierDto,
    SupplierListResponse,
    SupplierStatus,
    SupplierSummaryDto,
    SupplierUpdateRequest,
)
from app.services.supplier_service import (
    SupplierWithStats,
    create_supplier,
    get_supplier_detail,
    list_suppliers,
    update_supplier,
)

router = APIRouter(prefix="/workspaces/{workspaceId}/suppliers", tags=["Suppliers"])


def _to_supplier_summary_dto(item: SupplierWithStats) -> SupplierSummaryDto:
    s = item.supplier
    return SupplierSummaryDto(
        id=s.id,
        workspace_id=s.workspace_id,
        name=s.name,
        normalized_name=s.normalized_name,
        gstin=s.gstin,
        pan=s.pan,
        state_code=s.state_code,
        state_name=s.state_name,
        category=s.category,
        email=s.email,
        status=s.status,  # type: ignore[arg-type]
        created_at=s.created_at,
        updated_at=s.updated_at,
        total_invoices=item.total_invoices,
        total_value=item.total_value,
        last_invoice_date=item.last_invoice_date,
    )


@router.get(
    "",
    response_model=SupplierListResponse,
    response_model_by_alias=True,
    summary="List workspace suppliers with search, status filtering, pagination, and invoice aggregates",
)
def get_suppliers(
    ws_ctx: WorkspaceContext = Depends(
        require_workspace_role("WORKSPACE_ADMIN", "REVIEWER", "UPLOADER", "VIEWER")
    ),
    db: Session = Depends(get_db),
    search: str | None = Query(default=None, max_length=240),
    status_filter: SupplierStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100, alias="pageSize"),
) -> SupplierListResponse:
    items, total = list_suppliers(
        db,
        workspace_id=ws_ctx.workspace.id,
        search=search,
        status_filter=status_filter,
        page=page,
        page_size=page_size,
    )
    return SupplierListResponse(
        items=[_to_supplier_summary_dto(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=SupplierDto,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
    summary="Create a supplier master record inside the workspace (WORKSPACE_ADMIN, REVIEWER)",
)
def post_supplier(
    payload: SupplierCreateRequest,
    request: Request,
    ws_ctx: WorkspaceContext = Depends(
        require_workspace_role("WORKSPACE_ADMIN", "REVIEWER")
    ),
    db: Session = Depends(get_db),
) -> SupplierDto:
    supplier = create_supplier(
        db,
        workspace=ws_ctx.workspace,
        actor=ws_ctx.principal.user,
        payload=payload,
        ip_address=get_client_ip(request),
    )
    return SupplierDto.model_validate(supplier)


@router.get(
    "/{supplierId}",
    response_model=SupplierSummaryDto,
    response_model_by_alias=True,
    summary="Retrieve workspace supplier details and invoice aggregates",
)
def get_supplier(
    supplier_id: uuid.UUID = Path(..., alias="supplierId"),
    ws_ctx: WorkspaceContext = Depends(
        require_workspace_role("WORKSPACE_ADMIN", "REVIEWER", "UPLOADER", "VIEWER")
    ),
    db: Session = Depends(get_db),
) -> SupplierSummaryDto:
    item = get_supplier_detail(
        db,
        workspace_id=ws_ctx.workspace.id,
        supplier_id=supplier_id,
    )
    return _to_supplier_summary_dto(item)


@router.patch(
    "/{supplierId}",
    response_model=SupplierDto,
    response_model_by_alias=True,
    dependencies=[Depends(require_csrf)],
    summary="Update workspace supplier master details (WORKSPACE_ADMIN, REVIEWER)",
)
def patch_supplier(
    payload: SupplierUpdateRequest,
    request: Request,
    supplier_id: uuid.UUID = Path(..., alias="supplierId"),
    ws_ctx: WorkspaceContext = Depends(
        require_workspace_role("WORKSPACE_ADMIN", "REVIEWER")
    ),
    db: Session = Depends(get_db),
) -> SupplierDto:
    supplier = update_supplier(
        db,
        workspace=ws_ctx.workspace,
        supplier_id=supplier_id,
        actor=ws_ctx.principal.user,
        payload=payload,
        ip_address=get_client_ip(request),
    )
    return SupplierDto.model_validate(supplier)
