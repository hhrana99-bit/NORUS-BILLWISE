from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import WorkspaceContext, get_client_ip, require_workspace_role
from app.db.session import get_db
from app.schemas.invoices import InvoiceStatus, ReconciliationStatus
from app.schemas.reports import (
    MonthlyTrendResponse,
    ReportExceptionsResponse,
    ReportSummaryResponse,
    TrendWindow,
)
from app.schemas.review import FlagCategory
from app.services.report_service import (
    get_monthly_trend,
    get_report_summary,
    list_report_exceptions,
    prepare_and_stream_csv_export,
)

router = APIRouter(prefix="/workspaces/{workspaceId}/reports", tags=["Reports"])


@router.get(
    "/summary",
    response_model=ReportSummaryResponse,
    response_model_by_alias=True,
    summary="Compute workspace KPIs and GST totals across active invoices",
)
def get_workspace_report_summary(
    date_from: date | None = Query(default=None, alias="dateFrom"),
    date_to: date | None = Query(default=None, alias="dateTo"),
    currency: str | None = Query(default=None, min_length=3, max_length=3),
    ws_ctx: WorkspaceContext = Depends(
        require_workspace_role("WORKSPACE_ADMIN", "REVIEWER", "UPLOADER", "VIEWER")
    ),
    db: Session = Depends(get_db),
) -> ReportSummaryResponse:
    return get_report_summary(
        db,
        workspace_id=ws_ctx.workspace.id,
        date_from=date_from,
        date_to=date_to,
        currency=currency,
    )


@router.get(
    "/monthly-trend",
    response_model=MonthlyTrendResponse,
    response_model_by_alias=True,
    summary="Return chronological zero-filled monthly invoice volume and totals",
)
def get_workspace_monthly_trend(
    window: TrendWindow = Query(default="6m"),
    currency: str | None = Query(default=None, min_length=3, max_length=3),
    ws_ctx: WorkspaceContext = Depends(
        require_workspace_role("WORKSPACE_ADMIN", "REVIEWER", "UPLOADER", "VIEWER")
    ),
    db: Session = Depends(get_db),
) -> MonthlyTrendResponse:
    return get_monthly_trend(
        db,
        workspace_id=ws_ctx.workspace.id,
        window=window,
        currency=currency,
    )


@router.get(
    "/exceptions",
    response_model=ReportExceptionsResponse,
    response_model_by_alias=True,
    summary="List paginated flagged and unresolved-variance exception invoices",
)
def get_workspace_report_exceptions(
    search: str | None = Query(default=None, max_length=240),
    status_filter: InvoiceStatus | None = Query(default=None, alias="status"),
    flag_category: FlagCategory | None = Query(default=None, alias="flagCategory"),
    reconciliation_status: ReconciliationStatus | None = Query(
        default=None, alias="reconciliationStatus"
    ),
    date_from: date | None = Query(default=None, alias="dateFrom"),
    date_to: date | None = Query(default=None, alias="dateTo"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100, alias="pageSize"),
    ws_ctx: WorkspaceContext = Depends(
        require_workspace_role("WORKSPACE_ADMIN", "REVIEWER", "UPLOADER", "VIEWER")
    ),
    db: Session = Depends(get_db),
) -> ReportExceptionsResponse:
    return list_report_exceptions(
        db,
        workspace_id=ws_ctx.workspace.id,
        search=search,
        status_filter=status_filter,
        flag_category=flag_category,
        reconciliation_status=reconciliation_status,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/export.csv",
    summary="Export RFC-4180 CSV invoice register with formula-injection neutralization (ADMIN, REVIEWER, VIEWER)",
)
def export_workspace_report_csv(
    request: Request,
    status_filter: InvoiceStatus | None = Query(default=None, alias="status"),
    date_from: date | None = Query(default=None, alias="dateFrom"),
    date_to: date | None = Query(default=None, alias="dateTo"),
    currency: str | None = Query(default=None, min_length=3, max_length=3),
    ws_ctx: WorkspaceContext = Depends(
        require_workspace_role("WORKSPACE_ADMIN", "REVIEWER", "VIEWER")
    ),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    filename, stream = prepare_and_stream_csv_export(
        db,
        workspace=ws_ctx.workspace,
        actor=ws_ctx.principal.user,
        status_filter=status_filter,
        date_from=date_from,
        date_to=date_to,
        currency=currency,
        ip_address=get_client_ip(request),
    )
    return StreamingResponse(
        stream,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
