from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from typing import BinaryIO

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.accounting import Document, Invoice
from app.models.tenancy import User, Workspace, WorkspaceSettings, utc_now
from app.services.audit_service import record_audit_event
from app.services.storage_service import (
    MAX_DOCUMENT_BYTES,
    STREAM_CHUNK_SIZE,
    DocumentStorage,
    build_workspace_document_storage_key,
    sanitize_original_filename,
    validate_declared_upload_type,
    verify_magic_bytes_match_format,
)

logger = logging.getLogger(__name__)


def _clean_optional_text(value: str | None, *, max_len: int) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        return None
    return cleaned[:max_len]


def upload_workspace_document(
    db: Session,
    *,
    storage: DocumentStorage,
    workspace: Workspace,
    actor: User,
    raw_filename: str | None,
    declared_content_type: str | None,
    file_stream: BinaryIO,
    supplier_name: str | None = None,
    invoice_number: str | None = None,
    create_draft_invoice: bool = True,
    ip_address: str | None = None,
) -> tuple[Document, uuid.UUID | None]:
    """Validate and stream a document to storage, persist Document (+ optional draft Invoice), and emit audit."""
    expected_spec, safe_filename = validate_declared_upload_type(
        raw_filename=raw_filename,
        declared_content_type=declared_content_type,
    )

    document_id = uuid.uuid4()
    storage_key = build_workspace_document_storage_key(
        organization_id=workspace.organization_id,
        workspace_id=workspace.id,
        document_id=document_id,
        canonical_ext=expected_spec.canonical_ext,
    )

    stored = storage.save_stream(
        storage_key=storage_key,
        stream=file_stream,
        max_bytes=MAX_DOCUMENT_BYTES,
        chunk_size=STREAM_CHUNK_SIZE,
        header_validator=lambda hdr: verify_magic_bytes_match_format(
            hdr, expected_spec
        ),
    )

    try:
        # No real antivirus scanner is integrated in this milestone; scan_status remains PENDING
        # and content delivery strictly requires explicit CLEAN verification.
        document = Document(
            id=document_id,
            workspace_id=workspace.id,
            uploaded_by_user_id=actor.id,
            original_filename=safe_filename,
            storage_key=stored.storage_key,
            mime_type=expected_spec.canonical_mime,
            byte_size=stored.byte_size,
            sha256_checksum=stored.sha256_checksum,
            page_count=1,
            scan_status="PENDING",
        )
        db.add(document)
        db.flush()

        draft_invoice_id: uuid.UUID | None = None
        if create_draft_invoice:
            ws_settings = db.scalar(
                select(WorkspaceSettings).where(
                    WorkspaceSettings.workspace_id == workspace.id
                )
            )
            buyer_name = (
                ws_settings.legal_entity_name
                if ws_settings is not None
                else workspace.name
            )[:240]
            buyer_gstin = (
                ws_settings.company_gstin if ws_settings is not None else None
            )

            resolved_supplier_name = (
                _clean_optional_text(supplier_name, max_len=240)
                or "Pending Extraction"
            )
            resolved_invoice_number = (
                _clean_optional_text(invoice_number, max_len=100)
                or f"DRAFT-{str(document.id)[:8].upper()}"
            )
            normalized_invoice_number = resolved_invoice_number.strip().lower()[:100]

            draft_invoice = Invoice(
                workspace_id=workspace.id,
                document_id=document.id,
                supplier_name_snapshot=resolved_supplier_name,
                buyer_name_snapshot=buyer_name,
                buyer_gstin_snapshot=buyer_gstin,
                invoice_number=resolved_invoice_number,
                normalized_invoice_number=normalized_invoice_number,
                upload_date=utc_now().date(),
                status="PENDING_REVIEW",
                source_type="MANUAL_UPLOAD",
            )
            db.add(draft_invoice)
            db.flush()
            draft_invoice_id = draft_invoice.id

        record_audit_event(
            db,
            organization_id=workspace.organization_id,
            workspace_id=workspace.id,
            actor_user=actor,
            event_type="document.uploaded",
            entity_type="document",
            entity_id=document.id,
            summary=f"Uploaded document '{document.original_filename}' ({document.mime_type}, {document.scan_status}).",
            tone="neutral",
            metadata={
                "documentId": str(document.id),
                "mimeType": document.mime_type,
                "byteSize": document.byte_size,
                "scanStatus": document.scan_status,
                "invoiceId": str(draft_invoice_id) if draft_invoice_id else None,
            },
            ip_address=ip_address,
        )
        db.commit()
    except Exception:
        db.rollback()
        try:
            storage.delete(stored.storage_key)
        except Exception as cleanup_exc:
            logger.warning(
                "Failed to clean up document blob after DB rollback: type=%s",
                type(cleanup_exc).__name__,
            )
        raise

    db.refresh(document)
    return document, draft_invoice_id


def build_content_disposition(*, original_filename: str, download: bool) -> str:
    safe_name = sanitize_original_filename(original_filename)
    disposition = "attachment" if download else "inline"
    return f'{disposition}; filename="{safe_name}"'


def get_clean_document_stream(
    db: Session,
    *,
    storage: DocumentStorage,
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
) -> tuple[Document, Iterator[bytes]]:
    """Verify workspace ownership and explicit CLEAN scan status before opening content stream."""
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
            status_code=status.HTTP_403_FORBIDDEN,
            code="DOCUMENT_INFECTED",
            message="Document failed malware scanning and cannot be accessed.",
        )

    if document.scan_status != "CLEAN":
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="DOCUMENT_SCAN_NOT_CLEAN",
            message="Document content cannot be delivered until malware scanning confirms CLEAN status.",
        )

    stream = storage.open_stream(document.storage_key, chunk_size=STREAM_CHUNK_SIZE)
    return document, stream
