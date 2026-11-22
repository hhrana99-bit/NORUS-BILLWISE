from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, field_serializer, field_validator

from app.schemas.base import ApiModel
from app.schemas.invoices import (
    FlagCategory,
    InvoiceFieldVerificationInput,
    InvoiceReviewFlagDto,
    InvoiceStatus,
    canonicalize_field_key,
)

FlagResolutionStatus = Literal["RESOLVED", "DISMISSED"]
ReviewActionType = Literal[
    "SAVE_EDITS",
    "MARK_VERIFIED",
    "VERIFY_WITH_VARIANCE",
    "FLAG_INVOICE",
    "RESOLVE_FLAG",
    "REOPEN_PENDING",
]
ReviewHistoryOrder = Literal["asc", "desc"]
AuditTone = Literal["neutral", "success", "warning"]


def _reject_nul(value: str, *, field_label: str) -> str:
    if "\x00" in value:
        raise ValueError(f"{field_label} cannot contain NUL characters.")
    return value


class VerifyInvoiceRequest(ApiModel):
    confirm_variance_acknowledgment: bool = False
    confirmation_note: str = Field(default="", max_length=2000)
    resolve_open_flags: bool = False
    flag_resolution_note: str | None = Field(default=None, max_length=2000)
    field_verifications: list[InvoiceFieldVerificationInput] | None = Field(
        default=None, max_length=32
    )

    @field_validator("confirmation_note")
    @classmethod
    def validate_confirmation_note(cls, value: str) -> str:
        _reject_nul(value, field_label="confirmationNote")
        return value.strip()

    @field_validator("flag_resolution_note")
    @classmethod
    def validate_flag_resolution_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        _reject_nul(value, field_label="flagResolutionNote")
        return value.strip()

    @field_validator("field_verifications")
    @classmethod
    def validate_unique_field_keys(
        cls, value: list[InvoiceFieldVerificationInput] | None
    ) -> list[InvoiceFieldVerificationInput] | None:
        if value is None:
            return None
        keys = [item.field_key for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate fieldKey entries in fieldVerifications.")
        return value


class FlagInvoiceRequest(ApiModel):
    flag_category: FlagCategory = "CUSTOM"
    reason_text: str = Field(..., max_length=2000)
    field_key: str | None = Field(default=None, max_length=48)

    @field_validator("reason_text")
    @classmethod
    def validate_reason_text(cls, value: str) -> str:
        _reject_nul(value, field_label="reasonText")
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            raise ValueError("EMPTY_FLAG_REASON: reasonText cannot be blank.")
        return cleaned

    @field_validator("field_key")
    @classmethod
    def validate_optional_field_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("fieldKey cannot be blank when provided.")
        return canonicalize_field_key(value, field_label="fieldKey")


class ResolveFlagRequest(ApiModel):
    resolution_status: FlagResolutionStatus = "RESOLVED"
    resolution_note: str = Field(..., max_length=2000)
    reopen_to_pending: bool = True

    @field_validator("resolution_note")
    @classmethod
    def validate_resolution_note(cls, value: str) -> str:
        _reject_nul(value, field_label="resolutionNote")
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            raise ValueError(
                "INVALID_FLAG_RESOLUTION: resolutionNote cannot be blank."
            )
        return cleaned


class ReopenInvoiceRequest(ApiModel):
    reason: str = Field(..., max_length=2000)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        _reject_nul(value, field_label="reason")
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            raise ValueError("REOPEN_REASON_REQUIRED: reason cannot be blank.")
        return cleaned


class ResolveFlagResponse(ApiModel):
    flag: InvoiceReviewFlagDto
    invoice_id: uuid.UUID
    invoice_status: InvoiceStatus
    open_flag_count: int


class ReviewActionDto(ApiModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    invoice_id: uuid.UUID
    actor_user_id: uuid.UUID
    actor_display_name: str
    action_type: str
    previous_status: str
    new_status: str
    variance_acknowledged: bool
    variance_amount_at_action: Decimal | None = None
    comment: str | None = None
    field_changes: dict[str, Any] | None = None
    created_at: datetime

    @field_serializer("variance_amount_at_action")
    def serialize_variance_amount(self, value: Decimal | None) -> str | None:
        return f"{value:.2f}" if value is not None else None


class ReviewAuditEventDto(ApiModel):
    """Sanitized compliance audit entry exposed in review history (omits ipAddress)."""

    id: uuid.UUID
    organization_id: uuid.UUID
    workspace_id: uuid.UUID | None = None
    actor_user_id: uuid.UUID | None = None
    actor_display_name: str
    event_type: str
    entity_type: str
    entity_id: uuid.UUID | None = None
    summary: str
    tone: AuditTone
    metadata: dict[str, Any]
    created_at: datetime


class ReviewHistoryResponse(ApiModel):
    invoice_id: uuid.UUID
    status: InvoiceStatus
    actions: list[ReviewActionDto]
    flags: list[InvoiceReviewFlagDto]
    audit_events: list[ReviewAuditEventDto]
    total_actions: int
    total_flags: int
    total_audit_events: int
    page: int
    page_size: int


__all__ = [
    "FlagCategory",
    "FlagResolutionStatus",
    "FlagInvoiceRequest",
    "InvoiceReviewFlagDto",
    "ReopenInvoiceRequest",
    "ResolveFlagRequest",
    "ResolveFlagResponse",
    "ReviewActionDto",
    "ReviewActionType",
    "ReviewAuditEventDto",
    "ReviewHistoryOrder",
    "ReviewHistoryResponse",
    "VerifyInvoiceRequest",
]
