from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, field_serializer, field_validator, model_validator

from app.schemas.auth import OrgRole, WorkspaceRole, normalize_and_validate_email
from app.schemas.base import ApiModel

MembershipStatus = Literal["ACTIVE", "SUSPENDED"]


class OrganizationCreateRequest(ApiModel):
    name: str = Field(..., min_length=1, max_length=200)
    firm_type: str = Field(..., min_length=1, max_length=120)
    primary_contact_email: str = Field(..., min_length=5, max_length=255)

    @field_validator("name", "firm_type")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field cannot be blank.")
        return stripped

    @field_validator("primary_contact_email")
    @classmethod
    def validate_contact_email(cls, value: str) -> str:
        return normalize_and_validate_email(value)


class OrganizationDto(ApiModel):
    id: uuid.UUID
    name: str
    slug: str
    firm_type: str
    primary_contact_email: str
    role: OrgRole
    is_active: bool
    created_at: datetime


class OrganizationListResponse(ApiModel):
    items: list[OrganizationDto]


class WorkspaceCreateRequest(ApiModel):
    name: str = Field(..., min_length=1, max_length=200)
    workspace_code: str = Field(..., min_length=2, max_length=50)
    legal_entity_name: str = Field(..., min_length=1, max_length=240)
    company_gstin: str | None = Field(default=None, max_length=15)
    company_pan: str | None = Field(default=None, max_length=10)
    registered_address: str = Field(default="", max_length=1000)
    require_human_review: bool = True

    @field_validator("name", "legal_entity_name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field cannot be blank.")
        return stripped

    @field_validator("workspace_code")
    @classmethod
    def normalize_workspace_code(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned or any(ch.isspace() for ch in cleaned):
            raise ValueError("workspaceCode must not be blank or contain spaces.")
        return cleaned

    @field_validator("require_human_review")
    @classmethod
    def forbid_disabling_human_review(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("HUMAN_REVIEW_CANNOT_BE_DISABLED")
        return True


class WorkspaceListItemDto(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    workspace_code: str
    role: WorkspaceRole
    is_active: bool
    created_at: datetime


class WorkspaceListResponse(ApiModel):
    items: list[WorkspaceListItemDto]


class WorkspaceDetailDto(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    workspace_code: str
    is_active: bool
    current_user_role: WorkspaceRole
    created_at: datetime


class WorkspaceSettingsDto(ApiModel):
    workspace_id: uuid.UUID
    legal_entity_name: str
    company_gstin: str | None
    company_pan: str | None
    registered_address: str
    require_human_review: bool
    enable_duplicate_warnings: bool
    auto_flag_tax_mismatch: bool
    rounding_tolerance: Decimal
    default_currency: str
    financial_year: str
    date_format: str
    tax_regime: str
    notify_flagged_invoices: bool
    notify_daily_digest: bool
    notify_duplicate_alerts: bool
    updated_at: datetime

    @field_serializer("rounding_tolerance")
    def serialize_rounding_tolerance(self, value: Decimal) -> str:
        return f"{value:.2f}"


class WorkspaceProvisionResponse(ApiModel):
    workspace: WorkspaceDetailDto
    settings: WorkspaceSettingsDto


class WorkspaceSettingsUpdateRequest(ApiModel):
    legal_entity_name: str | None = Field(default=None, min_length=1, max_length=240)
    company_gstin: str | None = Field(default=None, max_length=15)
    company_pan: str | None = Field(default=None, max_length=10)
    registered_address: str | None = Field(default=None, max_length=1000)
    require_human_review: bool | None = None
    enable_duplicate_warnings: bool | None = None
    auto_flag_tax_mismatch: bool | None = None
    rounding_tolerance: Decimal | None = Field(default=None, ge=Decimal("0.00"), le=Decimal("10.00"))
    default_currency: str | None = Field(default=None, min_length=3, max_length=3)
    financial_year: str | None = Field(default=None, min_length=1, max_length=32)
    date_format: str | None = Field(default=None, min_length=1, max_length=20)
    tax_regime: str | None = Field(default=None, min_length=1, max_length=64)
    notify_flagged_invoices: bool | None = None
    notify_daily_digest: bool | None = None
    notify_duplicate_alerts: bool | None = None

    @field_validator("require_human_review")
    @classmethod
    def enforce_human_review_locked(cls, value: bool | None) -> bool | None:
        if value is False:
            raise ValueError("HUMAN_REVIEW_CANNOT_BE_DISABLED")
        return value

    @field_validator("legal_entity_name", "financial_year", "date_format", "tax_regime")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field cannot be blank.")
        return stripped

    @field_validator("default_currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().upper()
        if len(cleaned) != 3:
            raise ValueError("defaultCurrency must be a 3-letter ISO currency code.")
        return cleaned


class MembershipDto(ApiModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    role: WorkspaceRole
    status: MembershipStatus
    created_at: datetime
    updated_at: datetime


class MembershipListResponse(ApiModel):
    items: list[MembershipDto]


class MembershipCreateRequest(ApiModel):
    email: str = Field(..., min_length=5, max_length=255)
    role: WorkspaceRole

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_and_validate_email(value)


class MembershipUpdateRequest(ApiModel):
    role: WorkspaceRole | None = None
    status: MembershipStatus | None = None

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> MembershipUpdateRequest:
        if self.role is None and self.status is None:
            raise ValueError("At least one of 'role' or 'status' must be provided.")
        return self


class AuditEventDto(ApiModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    workspace_id: uuid.UUID | None
    actor_user_id: uuid.UUID | None
    actor_display_name: str
    event_type: str
    entity_type: str
    entity_id: uuid.UUID | None
    summary: str
    tone: Literal["neutral", "success", "warning"]
    metadata: dict[str, Any]
    created_at: datetime


class AuditEventListResponse(ApiModel):
    items: list[AuditEventDto]
    total: int
    page: int
    page_size: int
