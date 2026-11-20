from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from app.schemas.base import ApiModel

DocumentScanStatus = Literal["PENDING", "CLEAN", "INFECTED", "SKIPPED_DEV", "FAILED"]


class DocumentDto(ApiModel):
    """Public document metadata DTO; never exposes internal storage_key or filesystem paths."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    uploaded_by_user_id: uuid.UUID
    original_filename: str
    mime_type: str
    byte_size: int
    sha256_checksum: str
    page_count: int
    scan_status: DocumentScanStatus
    created_at: datetime


class DocumentUploadResponse(ApiModel):
    document: DocumentDto
    invoice_id: uuid.UUID | None = None
