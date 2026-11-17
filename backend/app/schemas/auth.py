from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from app.schemas.base import ApiModel

OrgRole = Literal["ORG_OWNER", "ORG_ADMIN", "ORG_MEMBER"]
WorkspaceRole = Literal["WORKSPACE_ADMIN", "REVIEWER", "UPLOADER", "VIEWER"]


def normalize_and_validate_email(raw_email: str) -> str:
    cleaned = raw_email.strip().lower()
    if not cleaned or "@" not in cleaned or any(ch.isspace() for ch in cleaned):
        raise ValueError("Invalid email address format.")
    local, domain = cleaned.split("@", 1)
    if not local or not domain or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise ValueError("Invalid email address format.")
    return cleaned


class RegisterRequest(ApiModel):
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=12, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=160)
    organization_name: str | None = Field(default=None, max_length=200)
    firm_type: str = Field(
        default="Chartered Accountancy Practice",
        min_length=1,
        max_length=120,
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_and_validate_email(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        non_ws = re.sub(r"\s+", "", value)
        if len(non_ws) < 12:
            raise ValueError("Password must contain at least 12 non-whitespace characters.")
        return value

    @field_validator("full_name", "firm_type")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field cannot be blank.")
        return stripped

    @field_validator("organization_name")
    @classmethod
    def validate_org_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class LoginRequest(ApiModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_and_validate_email(value)


class UserSummaryDto(ApiModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool = True


class OrganizationMembershipSummaryDto(ApiModel):
    id: uuid.UUID
    name: str
    slug: str
    firm_type: str
    role: OrgRole


class WorkspaceMembershipSummaryDto(ApiModel):
    workspace_id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    workspace_code: str
    role: WorkspaceRole


class RegisterResponse(ApiModel):
    user: UserSummaryDto
    organization: OrganizationMembershipSummaryDto | None = None
    workspace: WorkspaceMembershipSummaryDto | None = None
    session_expires_at: datetime


class LoginResponse(ApiModel):
    user: UserSummaryDto
    workspaces: list[WorkspaceMembershipSummaryDto]
    session_expires_at: datetime


class RefreshResponse(ApiModel):
    refreshed: bool = True
    session_expires_at: datetime


class MeResponse(ApiModel):
    user: UserSummaryDto
    organizations: list[OrganizationMembershipSummaryDto]
    workspaces: list[WorkspaceMembershipSummaryDto]
