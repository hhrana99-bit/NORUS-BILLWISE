from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    """Shared API schema enforcing camelCase JSON wire format and strict extra rejection."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )


class HealthResponse(ApiModel):
    status: str
    service: str
    environment: str


class ReadyResponse(ApiModel):
    status: str
    database: str
    detail: str | None = None


class ErrorDetail(ApiModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
    request_id: str | None = None


class ErrorResponse(ApiModel):
    error: ErrorDetail
