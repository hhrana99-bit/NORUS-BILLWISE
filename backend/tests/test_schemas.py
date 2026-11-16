from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.base import ApiModel, ErrorDetail, ErrorResponse, HealthResponse


class SampleAccountingDto(ApiModel):
    invoice_number: str
    taxable_amount: str
    is_reverse_charge: bool = False


def test_api_model_serializes_snake_case_to_camel_case() -> None:
    dto = SampleAccountingDto(
        invoice_number="INV-2026-001",
        taxable_amount="15000.00",
        is_reverse_charge=True,
    )

    payload = dto.model_dump(by_alias=True)
    assert payload == {
        "invoiceNumber": "INV-2026-001",
        "taxableAmount": "15000.00",
        "isReverseCharge": True,
    }


def test_api_model_accepts_camel_case_or_snake_case_input() -> None:
    from_camel = SampleAccountingDto.model_validate(
        {
            "invoiceNumber": "INV-2026-002",
            "taxableAmount": "900.00",
            "isReverseCharge": False,
        }
    )
    assert from_camel.invoice_number == "INV-2026-002"
    assert from_camel.taxable_amount == "900.00"
    assert from_camel.is_reverse_charge is False

    from_snake = SampleAccountingDto.model_validate(
        {
            "invoice_number": "INV-2026-003",
            "taxable_amount": "1200.50",
        }
    )
    assert from_snake.invoice_number == "INV-2026-003"


def test_api_model_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SampleAccountingDto.model_validate(
            {
                "invoiceNumber": "INV-2026-004",
                "taxableAmount": "500.00",
                "unexpectedField": "boom",
            }
        )


def test_shared_response_dtos_use_camel_case() -> None:
    health = HealthResponse(status="ok", service="norus-billwise-api", environment="test")
    assert health.model_dump(by_alias=True) == {
        "status": "ok",
        "service": "norus-billwise-api",
        "environment": "test",
    }

    error = ErrorResponse(
        error=ErrorDetail(
            code="VALIDATION_ERROR",
            message="Invalid request payload",
            request_id="req_12345",
        )
    )
    dumped = error.model_dump(by_alias=True)
    assert "requestId" in dumped["error"]
    assert dumped["error"]["requestId"] == "req_12345"
