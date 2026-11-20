from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_serializer, field_validator, model_validator
from pydantic.alias_generators import to_camel

from app.schemas.auth import normalize_and_validate_email
from app.schemas.base import ApiModel
from app.schemas.tenancy import (
    normalize_and_validate_gstin,
    normalize_and_validate_pan,
)

SupplierStatus = Literal["VERIFIED", "NEEDS_VERIFICATION", "FLAGGED"]

_STATE_CODE_REGEX = re.compile(r"^[0-9]{2}$")


def clean_supplier_display_name(value: str) -> str:
    """Trim leading/trailing whitespace and collapse repeated whitespace for display names."""
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        raise ValueError("Supplier name cannot be blank.")
    return cleaned


def normalize_supplier_name(value: str) -> str:
    """Compute canonical normalized supplier name (trimmed, collapsed whitespace, lowercased)."""
    return clean_supplier_display_name(value).lower()


def _normalize_optional_state_code(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if not _STATE_CODE_REGEX.fullmatch(cleaned):
        raise ValueError("stateCode must be a 2-digit Indian GST state code.")
    return cleaned


def _normalize_optional_state_name(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.strip().split())
    return cleaned or None


def _normalize_optional_email(value: str | None) -> str | None:
    if value is None:
        return None
    if not value.strip():
        return None
    return normalize_and_validate_email(value)


def _normalize_category(value: str) -> str:
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        raise ValueError("category cannot be blank.")
    return cleaned


def _strip_optional_text(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    return value


class SupplierCreateRequest(ApiModel):
    name: str = Field(..., min_length=1, max_length=240)
    gstin: str | None = Field(default=None, max_length=15)
    pan: str | None = Field(default=None, max_length=10)
    state_code: str | None = Field(default=None, max_length=2)
    state_name: str | None = Field(default=None, max_length=80)
    category: str = Field(default="General", min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=255)
    status: SupplierStatus = "NEEDS_VERIFICATION"

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return clean_supplier_display_name(value)

    @field_validator("gstin", "pan", mode="before")
    @classmethod
    def strip_tax_ids_before_length_check(cls, value: object) -> object:
        return _strip_optional_text(value)

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, value: str | None) -> str | None:
        return normalize_and_validate_gstin(value, field_label="gstin")

    @field_validator("pan")
    @classmethod
    def validate_pan(cls, value: str | None) -> str | None:
        return normalize_and_validate_pan(value, field_label="pan")

    @field_validator("state_code")
    @classmethod
    def validate_state_code(cls, value: str | None) -> str | None:
        return _normalize_optional_state_code(value)

    @field_validator("state_name")
    @classmethod
    def validate_state_name(cls, value: str | None) -> str | None:
        return _normalize_optional_state_name(value)

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        return _normalize_category(value)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        return _normalize_optional_email(value)


class SupplierUpdateRequest(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=240)
    gstin: str | None = Field(default=None, max_length=15)
    pan: str | None = Field(default=None, max_length=10)
    state_code: str | None = Field(default=None, max_length=2)
    state_name: str | None = Field(default=None, max_length=80)
    category: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=255)
    status: SupplierStatus | None = None

    @model_validator(mode="after")
    def validate_patch_payload(self) -> SupplierUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided for update.")

        for non_nullable in ("name", "category", "status"):
            if (
                non_nullable in self.model_fields_set
                and getattr(self, non_nullable) is None
            ):
                raise ValueError(f"{to_camel(non_nullable)} cannot be null.")
        return self

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return clean_supplier_display_name(value)

    @field_validator("gstin", "pan", mode="before")
    @classmethod
    def strip_tax_ids_before_length_check(cls, value: object) -> object:
        return _strip_optional_text(value)

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, value: str | None) -> str | None:
        return normalize_and_validate_gstin(value, field_label="gstin")

    @field_validator("pan")
    @classmethod
    def validate_pan(cls, value: str | None) -> str | None:
        return normalize_and_validate_pan(value, field_label="pan")

    @field_validator("state_code")
    @classmethod
    def validate_state_code(cls, value: str | None) -> str | None:
        return _normalize_optional_state_code(value)

    @field_validator("state_name")
    @classmethod
    def validate_state_name(cls, value: str | None) -> str | None:
        return _normalize_optional_state_name(value)

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_category(value)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        return _normalize_optional_email(value)


class SupplierDto(ApiModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    normalized_name: str
    gstin: str | None
    pan: str | None
    state_code: str | None
    state_name: str | None
    category: str
    email: str | None
    status: SupplierStatus
    created_at: datetime
    updated_at: datetime


class SupplierSummaryDto(SupplierDto):
    total_invoices: int = 0
    total_value: Decimal = Decimal("0.00")
    last_invoice_date: date | None = None

    @field_serializer("total_value")
    def serialize_total_value(self, value: Decimal) -> str:
        return f"{value:.2f}"


class SupplierListResponse(ApiModel):
    items: list[SupplierSummaryDto]
    total: int
    page: int
    page_size: int
