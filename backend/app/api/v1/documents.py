from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Path, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import (
    WorkspaceContext,
    get_app_settings,
    get_client_ip,
    require_csrf,
    require_workspace_role,
)
from app.db.session import get_db
from app.schemas.documents import DocumentDto, DocumentUploadResponse
from app.services.document_service import (
    build_content_disposition,
    get_clean_document_stream,
    upload_workspace_document,
)
from app.services.storage_service import DocumentStorage, LocalFilesystemStorage

router = APIRouter(prefix="/workspaces/{workspaceId}/documents", tags=["Documents"])


def get_document_storage(
    settings: Settings = Depends(get_app_settings),
) -> DocumentStorage:
    return LocalFilesystemStorage(settings.document_storage_root)


@router.post(
    "",
    response_model=DocumentUploadResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
    summary="Upload and validate a PDF/PNG/JPEG/WEBP invoice document (WORKSPACE_ADMIN, REVIEWER, UPLOADER)",
)
def post_document(
    request: Request,
    file: UploadFile = File(...),
    supplier_name: str | None = Form(default=None, alias="supplierName", max_length=240),
    invoice_number: str | None = Form(default=None, alias="invoiceNumber", max_length=100),
    create_draft_invoice: bool = Form(default=True, alias="createDraftInvoice"),
    ws_ctx: WorkspaceContext = Depends(
        require_workspace_role("WORKSPACE_ADMIN", "REVIEWER", "UPLOADER")
    ),
    db: Session = Depends(get_db),
    storage: DocumentStorage = Depends(get_document_storage),
) -> DocumentUploadResponse:
    document, invoice_id = upload_workspace_document(
        db,
        storage=storage,
        workspace=ws_ctx.workspace,
        actor=ws_ctx.principal.user,
        raw_filename=file.filename,
        declared_content_type=file.content_type,
        file_stream=file.file,
        supplier_name=supplier_name,
        invoice_number=invoice_number,
        create_draft_invoice=create_draft_invoice,
        ip_address=get_client_ip(request),
    )
    return DocumentUploadResponse(
        document=DocumentDto.model_validate(document),
        invoice_id=invoice_id,
    )


@router.get(
    "/{documentId}/content",
    summary="Stream a verified CLEAN document safely to active workspace members",
)
def get_document_content(
    document_id: uuid.UUID = Path(..., alias="documentId"),
    download: bool = Query(default=False),
    ws_ctx: WorkspaceContext = Depends(
        require_workspace_role("WORKSPACE_ADMIN", "REVIEWER", "UPLOADER", "VIEWER")
    ),
    db: Session = Depends(get_db),
    storage: DocumentStorage = Depends(get_document_storage),
) -> StreamingResponse:
    document, stream = get_clean_document_stream(
        db,
        storage=storage,
        workspace_id=ws_ctx.workspace.id,
        document_id=document_id,
    )
    content_disposition = build_content_disposition(
        original_filename=document.original_filename,
        download=download,
    )
    return StreamingResponse(
        stream,
        media_type=document.mime_type,
        headers={
            "Content-Disposition": content_disposition,
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "Content-Length": str(document.byte_size),
        },
    )
