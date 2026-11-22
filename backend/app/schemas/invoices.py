from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, field_serializer, field_validator, model_validator
from pydantic.alias_generators import to_camel

from app.schemas.base import ApiModel
from app.schemas.documents import DocumentScanStatus
from app.schemas.tenancy import normalize_and_validate_gstin

InvoiceStatus = Literal["PENDING_REVIEW", "VERIFIED", "FLAGGED"]
DiscountMode = Literal["NONE", "PRE_TAX", "POST_TAX_COMMERCIAL"]
ReconciliationStatus = Literal[
    "MATCHED",
    "WITHIN_ROUNDING_TOLERANCE",
    "VARIANCE_DETECTED",
    "PENDING_INPUT",
]
LineItemReconciliationStatus = Literal[
    "NO_LINE_ITEMS",
    "MATCHED",
    "VARIANCE_WARNING",
]
InvoiceSourceType = Literal[
    "MANUAL_UPLOAD",
    "MANUAL_ENTRY",
    "OCR_EXTRACTED",
    "SEED_DEMO",
]
TaxTypeFilter = Literal["INTRA_STATE", "INTER_STATE"]
InvoiceTaxType = Literal["INTRA_STATE", "INTER_STATE", "MIXED", "NO_GST"]
InvoiceSortBy = Literal[
    "invoiceNumber",
    "supplierName",
    "invoiceDate",
    "totalAmount",
    "taxAmount",
    "status",
    "uploadDate",
]
SortDirection = Literal["asc", "desc"]
FieldVerificationStatus = Literal["VERIFIED", "NEEDS_REVIEW", "FLAGGED"]
DiscrepancySeverity = Literal["INFO", "WARNING"]
DuplicateMatchReason = Literal[
    "NORMALIZED_INVOICE_NUMBER",
    "SIMILAR_TOTAL_WITHIN_45_DAYS",
]

_STATE_CODE_REGEX = re.compile(r"^[0-9]{2}$")
_FINANCIAL_YEAR_REGEX = re.compile(r"^([0-9]{4})-([0-9]{2}|[0-9]{4})$")
_ALLOWED_FIELD_KEYS = frozenset(
    {
        "supplier_name",
        "supplier_gstin",
        "buyer_name",
        "buyer_gstin",
        "place_of_supply_code",
        "invoice_number",
        "invoice_date",
        "due_date",
        "taxable_amount",
        "discount_amount",
        "cgst_amount",
        "sgst_amount",
        "igst_amount",
        "cess_amount",
        "freight_amount",
        "other_charges_amount",
        "round_off_amount",
        "total_amount",
    }
)


def _ensure_no_nul(value: str, *, field_label: str) -> str:
    if "\x00" in value:
        raise ValueError(f"{field_label} cannot contain NUL characters.")
    return value


def _clean_required_text(value: str, *, field_label: str) -> str:
    _ensure_no_nul(value, field_label=field_label)
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        raise ValueError(f"{field_label} cannot be blank.")
    return cleaned


def _clean_optional_text(value: str | None, *, field_label: str) -> str | None:
    if value is None:
        return None
    _ensure_no_nul(value, field_label=field_label)
    cleaned = " ".join(value.strip().split())
    return cleaned or None


def _clean_optional_note(value: str | None, *, field_label: str) -> str | None:
    if value is None:
        return None
    _ensure_no_nul(value, field_label=field_label)
    return value.strip()


def _normalize_optional_state_code(value: str | None) -> str | None:
    if value is None:
        return None
    _ensure_no_nul(value, field_label="placeOfSupplyCode")
    cleaned = value.strip()
    if not cleaned:
        return None
    if not _STATE_CODE_REGEX.fullmatch(cleaned):
        raise ValueError("placeOfSupplyCode must be a 2-digit Indian GST state code.")
    return cleaned


def _normalize_currency(value: str) -> str:
    _ensure_no_nul(value, field_label="currency")
    cleaned = value.strip().upper()
    if len(cleaned) != 3 or not cleaned.isalpha():
        raise ValueError("currency must be a 3-letter ISO currency code.")
    return cleaned


def _normalize_supplier_gstin_snapshot(value: str | None) -> str | None:
    if value is None:
        return None
    _ensure_no_nul(value, field_label="supplierGstin")
    cleaned = " ".join(value.strip().split()).upper()
    if not cleaned:
        return None
    if len(cleaned) > 20:
        raise ValueError("supplierGstin must be at most 20 characters.")
    return cleaned


def _validate_finite_decimal(value: Decimal, *, field_label: str) -> Decimal:
    if not value.is_finite():
        raise ValueError(f"{field_label} must be a finite decimal number.")
    return value


def _strip_optional_str(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    return value


def parse_financial_year_bounds(financial_year: str) -> tuple[date, date]:
    """Parse 'YYYY-YY' or 'YYYY-YYYY' into Indian April–March date bounds."""
    cleaned = financial_year.strip()
    match = _FINANCIAL_YEAR_REGEX.fullmatch(cleaned)
    if match is None:
        raise ValueError("financialYear must use YYYY-YY format (for example, 2026-27).")
    start_year = int(match.group(1))
    end_part = match.group(2)
    expected_two_digit = f"{(start_year + 1) % 100:02d}"
    expected_four_digit = f"{start_year + 1:04d}"
    if end_part not in {expected_two_digit, expected_four_digit}:
        raise ValueError(
            "financialYear end year must immediately follow start year (for example, 2026-27)."
        )
    return date(start_year, 4, 1), date(start_year + 1, 3, 31)


class InvoiceLineItemInput(ApiModel):
    sort_order: int | None = Field(default=None, ge=0, le=10000)
    description: str = Field(..., min_length=1, max_length=1000)
    hsn_sac: str = Field(default="", max_length=16)
    quantity: Decimal = Field(
        default=Decimal("1.0000"),
        ge=Decimal("0.0000"),
        max_digits=14,
        decimal_places=4,
    )
    unit: str = Field(default="NOS", min_length=1, max_length=24)
    unit_price: Decimal = Field(
        default=Decimal("0.0000"),
        ge=Decimal("0.0000"),
        max_digits=14,
        decimal_places=4,
    )
    discount_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )
    taxable_value: Decimal | None = Field(
        default=None,
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )
    tax_rate_percent: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        le=Decimal("100.00"),
        max_digits=5,
        decimal_places=2,
    )
    cgst_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )
    sgst_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )
    igst_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )
    cess_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )
    line_total: Decimal | None = Field(
        default=None,
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        return _clean_required_text(value, field_label="lineItems[].description")

    @field_validator("hsn_sac")
    @classmethod
    def validate_hsn_sac(cls, value: str) -> str:
        _ensure_no_nul(value, field_label="lineItems[].hsnSac")
        return " ".join(value.strip().split()).upper()

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, value: str) -> str:
        return _clean_required_text(value, field_label="lineItems[].unit").upper()

    @field_validator(
        "quantity",
        "unit_price",
        "discount_amount",
        "taxable_value",
        "tax_rate_percent",
        "cgst_amount",
        "sgst_amount",
        "igst_amount",
        "cess_amount",
        "line_total",
    )
    @classmethod
    def check_finite_decimals(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        return _validate_finite_decimal(value, field_label="lineItem amount")


class InvoiceFieldVerificationInput(ApiModel):
    field_key: str = Field(..., min_length=1, max_length=48)
    status: FieldVerificationStatus = "NEEDS_REVIEW"
    evidence_note: str = Field(default="", max_length=1000)
    source_page: int | None = Field(default=None, ge=1, le=10000)
    bounding_box: dict[str, Any] | None = None
    confidence_score: Decimal | None = Field(
        default=None,
        ge=Decimal("0.000"),
        le=Decimal("1.000"),
        max_digits=4,
        decimal_places=3,
    )

    @field_validator("field_key")
    @classmethod
    def validate_field_key(cls, value: str) -> str:
        _ensure_no_nul(value, field_label="fieldVerifications[].fieldKey")
        cleaned = value.strip()
        if cleaned not in _ALLOWED_FIELD_KEYS:
            raise ValueError(f"Unsupported fieldKey: {cleaned!r}.")
        return cleaned

    @field_validator("evidence_note")
    @classmethod
    def validate_evidence_note(cls, value: str) -> str:
        _ensure_no_nul(value, field_label="fieldVerifications[].evidenceNote")
        return value.strip()


class InvoiceCreateRequest(ApiModel):
    supplier_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None

    supplier_name: str | None = Field(default=None, max_length=240)
    supplier_gstin: str | None = Field(default=None, max_length=20)
    buyer_name: str | None = Field(default=None, max_length=240)
    buyer_gstin: str | None = Field(default=None, max_length=15)
    place_of_supply_code: str | None = Field(default=None, max_length=2)
    place_of_supply_name: str | None = Field(default=None, max_length=80)

    invoice_number: str = Field(..., min_length=1, max_length=100)
    invoice_date: date | None = None
    due_date: date | None = None
    upload_date: date | None = None
    currency: str = Field(default="INR", min_length=3, max_length=3)
    is_reverse_charge: bool = False
    source_type: InvoiceSourceType | None = None

    taxable_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )
    discount_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )
    discount_mode: DiscountMode = "NONE"
    cgst_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )
    sgst_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )
    igst_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )
    cess_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )
    freight_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )
    other_charges_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )
    round_off_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("-9999999999.99"),
        le=Decimal("9999999999.99"),
        max_digits=14,
        decimal_places=2,
    )
    total_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )

    reviewer_note: str = Field(default="", max_length=4000)
    line_items: list[InvoiceLineItemInput] = Field(default_factory=list, max_length=500)
    field_verifications: list[InvoiceFieldVerificationInput] = Field(
        default_factory=list, max_length=32
    )

    @field_validator("buyer_gstin", mode="before")
    @classmethod
    def strip_buyer_gstin_before_length(cls, value: object) -> object:
        return _strip_optional_str(value)

    @field_validator("currency", mode="before")
    @classmethod
    def strip_currency_before_length(cls, value: object) -> object:
        return _strip_optional_str(value)

    @field_validator("invoice_number")
    @classmethod
    def validate_invoice_number(cls, value: str) -> str:
        return _clean_required_text(value, field_label="invoiceNumber")

    @field_validator("supplier_name", "buyer_name", "place_of_supply_name")
    @classmethod
    def validate_optional_names(cls, value: str | None) -> str | None:
        return _clean_optional_text(value, field_label="text")

    @field_validator("supplier_gstin")
    @classmethod
    def validate_supplier_gstin(cls, value: str | None) -> str | None:
        return _normalize_supplier_gstin_snapshot(value)

    @field_validator("buyer_gstin")
    @classmethod
    def validate_buyer_gstin(cls, value: str | None) -> str | None:
        if value is not None:
            _ensure_no_nul(value, field_label="buyerGstin")
        return normalize_and_validate_gstin(value, field_label="buyerGstin")

    @field_validator("place_of_supply_code")
    @classmethod
    def validate_place_of_supply_code(cls, value: str | None) -> str | None:
        return _normalize_optional_state_code(value)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return _normalize_currency(value)

    @field_validator("reviewer_note")
    @classmethod
    def validate_reviewer_note(cls, value: str) -> str:
        cleaned = _clean_optional_note(value, field_label="reviewerNote")
        return cleaned or ""

    @field_validator(
        "taxable_amount",
        "discount_amount",
        "cgst_amount",
        "sgst_amount",
        "igst_amount",
        "cess_amount",
        "freight_amount",
        "other_charges_amount",
        "round_off_amount",
        "total_amount",
    )
    @classmethod
    def validate_monetary_finite(cls, value: Decimal) -> Decimal:
        return _validate_finite_decimal(value, field_label="amount")

    @model_validator(mode="after")
    def validate_cross_field_rules(self) -> InvoiceCreateRequest:
        if self.supplier_id is None and self.supplier_name is None:
            raise ValueError(
                "Either supplierId or a non-blank supplierName must be provided."
            )
        if (
            self.invoice_date is not None
            and self.due_date is not None
            and self.due_date < self.invoice_date
        ):
            raise ValueError("dueDate cannot be earlier than invoiceDate.")
        field_keys = [item.field_key for item in self.field_verifications]
        if len(field_keys) != len(set(field_keys)):
            raise ValueError("Duplicate fieldKey entries in fieldVerifications.")
        return self


class InvoiceUpdateRequest(ApiModel):
    supplier_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None

    supplier_name: str | None = Field(default=None, min_length=1, max_length=240)
    supplier_gstin: str | None = Field(default=None, max_length=20)
    buyer_name: str | None = Field(default=None, min_length=1, max_length=240)
    buyer_gstin: str | None = Field(default=None, max_length=15)
    place_of_supply_code: str | None = Field(default=None, max_length=2)
    place_of_supply_name: str | None = Field(default=None, max_length=80)

    invoice_number: str | None = Field(default=None, min_length=1, max_length=100)
    invoice_date: date | None = None
    due_date: date | None = None
    upload_date: date | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    is_reverse_charge: bool | None = None

    taxable_amount: Decimal | None = Field(
        default=None,
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )
    discount_amount: Decimal | None = Field(
        default=None,
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )
    discount_mode: DiscountMode | None = None
    cgst_amount: Decimal | None = Field(
        default=None,
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )
    sgst_amount: Decimal | None = Field(
        default=None,
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )
    igst_amount: Decimal | None = Field(
        default=None,
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )
    cess_amount: Decimal | None = Field(
        default=None,
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )
    freight_amount: Decimal | None = Field(
        default=None,
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )
    other_charges_amount: Decimal | None = Field(
        default=None,
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )
    round_off_amount: Decimal | None = Field(
        default=None,
        ge=Decimal("-9999999999.99"),
        le=Decimal("9999999999.99"),
        max_digits=14,
        decimal_places=2,
    )
    total_amount: Decimal | None = Field(
        default=None,
        ge=Decimal("0.00"),
        max_digits=14,
        decimal_places=2,
    )

    reviewer_note: str | None = Field(default=None, max_length=4000)
    line_items: list[InvoiceLineItemInput] | None = Field(default=None, max_length=500)
    field_verifications: list[InvoiceFieldVerificationInput] | None = Field(
        default=None, max_length=32
    )

    @field_validator("buyer_gstin", mode="before")
    @classmethod
    def strip_buyer_gstin_before_length(cls, value: object) -> object:
        return _strip_optional_str(value)

    @field_validator("currency", mode="before")
    @classmethod
    def strip_currency_before_length(cls, value: object) -> object:
        return _strip_optional_str(value)

    @field_validator("invoice_number")
    @classmethod
    def validate_invoice_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_required_text(value, field_label="invoiceNumber")

    @field_validator("supplier_name", "buyer_name")
    @classmethod
    def validate_non_blank_optional_names(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_required_text(value, field_label="name")

    @field_validator("place_of_supply_name")
    @classmethod
    def validate_place_of_supply_name(cls, value: str | None) -> str | None:
        return _clean_optional_text(value, field_label="placeOfSupplyName")

    @field_validator("supplier_gstin")
    @classmethod
    def validate_supplier_gstin(cls, value: str | None) -> str | None:
        return _normalize_supplier_gstin_snapshot(value)

    @field_validator("buyer_gstin")
    @classmethod
    def validate_buyer_gstin(cls, value: str | None) -> str | None:
        if value is not None:
            _ensure_no_nul(value, field_label="buyerGstin")
        return normalize_and_validate_gstin(value, field_label="buyerGstin")

    @field_validator("place_of_supply_code")
    @classmethod
    def validate_place_of_supply_code(cls, value: str | None) -> str | None:
        return _normalize_optional_state_code(value)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_currency(value)

    @field_validator("reviewer_note")
    @classmethod
    def validate_reviewer_note(cls, value: str | None) -> str | None:
        return _clean_optional_note(value, field_label="reviewerNote")

    @field_validator(
        "taxable_amount",
        "discount_amount",
        "cgst_amount",
        "sgst_amount",
        "igst_amount",
        "cess_amount",
        "freight_amount",
        "other_charges_amount",
        "round_off_amount",
        "total_amount",
    )
    @classmethod
    def validate_monetary_finite(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        return _validate_finite_decimal(value, field_label="amount")

    @model_validator(mode="after")
    def validate_patch_payload(self) -> InvoiceUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided for update.")

        non_nullable = (
            "supplier_name",
            "buyer_name",
            "invoice_number",
            "upload_date",
            "currency",
            "is_reverse_charge",
            "taxable_amount",
            "discount_amount",
            "discount_mode",
            "cgst_amount",
            "sgst_amount",
            "igst_amount",
            "cess_amount",
            "freight_amount",
            "other_charges_amount",
            "round_off_amount",
            "total_amount",
            "reviewer_note",
            "line_items",
            "field_verifications",
        )
        for field_name in non_nullable:
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{to_camel(field_name)} cannot be null.")

        if self.field_verifications is not None:
            field_keys = [item.field_key for item in self.field_verifications]
            if len(field_keys) != len(set(field_keys)):
                raise ValueError("Duplicate fieldKey entries in fieldVerifications.")
        return self


class InvoiceDeleteRequest(ApiModel):
    deletion_reason: str | None = Field(default=None, max_length=1000)

    @field_validator("deletion_reason")
    @classmethod
    def validate_deletion_reason(cls, value: str | None) -> str | None:
        return _clean_optional_text(value, field_label="deletionReason")


class InvoiceLineItemDto(ApiModel):
    id: uuid.UUID
    sort_order: int
    description: str
    hsn_sac: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    discount_amount: Decimal
    taxable_value: Decimal
    tax_rate_percent: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    cess_amount: Decimal
    line_total: Decimal

    @field_serializer("quantity", "unit_price")
    def serialize_four_dp(self, value: Decimal) -> str:
        return f"{value:.4f}"

    @field_serializer(
        "discount_amount",
        "taxable_value",
        "tax_rate_percent",
        "cgst_amount",
        "sgst_amount",
        "igst_amount",
        "cess_amount",
        "line_total",
    )
    def serialize_two_dp(self, value: Decimal) -> str:
        return f"{value:.2f}"


class InvoiceFieldVerificationDto(ApiModel):
    id: uuid.UUID
    field_key: str
    status: FieldVerificationStatus
    evidence_note: str
    source_page: int | None
    bounding_box: dict[str, Any] | None
    confidence_score: Decimal | None
    verified_by_user_id: uuid.UUID | None
    updated_at: datetime

    @field_serializer("confidence_score")
    def serialize_confidence(self, value: Decimal | None) -> str | None:
        return f"{value:.3f}" if value is not None else None


class InvoiceDocumentDescriptorDto(ApiModel):
    """Public preview descriptor for a linked document (never exposes storage_key)."""

    id: uuid.UUID
    original_filename: str
    mime_type: str
    byte_size: int
    page_count: int
    scan_status: DocumentScanStatus


class ReconciliationDiscrepancyDto(ApiModel):
    code: str
    severity: DiscrepancySeverity
    message: str
    details: dict[str, Any] | None = None


class InvoiceReconciliationSummaryDto(ApiModel):
    rounding_tolerance: Decimal
    computed_expected_total: Decimal
    declared_total: Decimal
    variance_amount: Decimal
    reconciliation_status: ReconciliationStatus
    line_items_taxable_sum: Decimal | None
    line_item_variance_amount: Decimal | None
    line_item_reconciliation_status: LineItemReconciliationStatus
    line_item_warning: str | None
    discrepancies: list[ReconciliationDiscrepancyDto]

    @field_serializer(
        "rounding_tolerance",
        "computed_expected_total",
        "declared_total",
        "variance_amount",
    )
    def serialize_money(self, value: Decimal) -> str:
        return f"{value:.2f}"

    @field_serializer("line_items_taxable_sum", "line_item_variance_amount")
    def serialize_optional_money(self, value: Decimal | None) -> str | None:
        return f"{value:.2f}" if value is not None else None


class DuplicateMatchDto(ApiModel):
    invoice_id: uuid.UUID
    invoice_number: str
    invoice_date: date | None
    total_amount: Decimal
    status: InvoiceStatus
    match_reasons: list[DuplicateMatchReason]

    @field_serializer("total_amount")
    def serialize_total_amount(self, value: Decimal) -> str:
        return f"{value:.2f}"


class InvoiceSummaryDto(ApiModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    supplier_id: uuid.UUID | None
    document_id: uuid.UUID | None

    supplier_name: str
    supplier_gstin: str
    buyer_name: str
    buyer_gstin: str | None
    place_of_supply_code: str | None
    place_of_supply_name: str | None

    invoice_number: str
    normalized_invoice_number: str
    invoice_date: date | None
    due_date: date | None
    upload_date: date
    financial_year: str | None
    currency: str
    is_reverse_charge: bool
    tax_type: InvoiceTaxType

    taxable_amount: Decimal
    discount_amount: Decimal
    discount_mode: DiscountMode
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    cess_amount: Decimal
    tax_amount: Decimal
    freight_amount: Decimal
    other_charges_amount: Decimal
    round_off_amount: Decimal
    total_amount: Decimal

    computed_expected_total: Decimal
    variance_amount: Decimal
    reconciliation_status: ReconciliationStatus
    line_items_taxable_sum: Decimal | None
    line_item_variance_amount: Decimal | None
    line_item_reconciliation_status: LineItemReconciliationStatus
    line_item_warning: str | None

    status: InvoiceStatus
    duplicate_warning: str | None
    reviewer_note: str
    source_type: InvoiceSourceType
    verified_by_user_id: uuid.UUID | None
    verified_at: datetime | None
    line_item_count: int = 0
    open_flag_count: int = 0
    created_at: datetime
    updated_at: datetime

    @field_serializer(
        "taxable_amount",
        "discount_amount",
        "cgst_amount",
        "sgst_amount",
        "igst_amount",
        "cess_amount",
        "tax_amount",
        "freight_amount",
        "other_charges_amount",
        "round_off_amount",
        "total_amount",
        "computed_expected_total",
        "variance_amount",
    )
    def serialize_two_dp(self, value: Decimal) -> str:
        return f"{value:.2f}"

    @field_serializer("line_items_taxable_sum", "line_item_variance_amount")
    def serialize_optional_two_dp(self, value: Decimal | None) -> str | None:
        return f"{value:.2f}" if value is not None else None


class InvoiceDetailDto(InvoiceSummaryDto):
    document: InvoiceDocumentDescriptorDto | None = None
    line_items: list[InvoiceLineItemDto] = Field(default_factory=list)
    field_verifications: list[InvoiceFieldVerificationDto] = Field(default_factory=list)
    reconciliation: InvoiceReconciliationSummaryDto
    duplicate_matches: list[DuplicateMatchDto] = Field(default_factory=list)


class InvoiceListResponse(ApiModel):
    items: list[InvoiceSummaryDto]
    total: int
    page: int
    page_size: int
