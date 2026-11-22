from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.schemas.invoices import (
    DiscountMode,
    DiscrepancySeverity,
    InvoiceLineItemInput,
    InvoiceTaxType,
    LineItemReconciliationStatus,
    ReconciliationStatus,
)

TWO_DP = Decimal("0.01")
FOUR_DP = Decimal("0.0001")
ZERO = Decimal("0.00")
DEFAULT_ROUNDING_TOLERANCE = Decimal("1.00")
EXCESSIVE_ROUND_OFF_THRESHOLD = Decimal("10.00")

_GSTIN_REGEX = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_ALNUM_RUN_REGEX = re.compile(r"[a-z0-9]+")
_ALPHA_DIGIT_BOUNDARY_REGEX = re.compile(
    r"(?<=[a-z])-(?=[0-9])|(?<=[0-9])-(?=[a-z])"
)


def quantize_money(value: Decimal) -> Decimal:
    """Round currency values deterministically using financial half-up to 2 decimal places."""
    return value.quantize(TWO_DP, rounding=ROUND_HALF_UP)


def quantize_qty(value: Decimal) -> Decimal:
    """Round line-item quantities and unit prices to 4 decimal places."""
    return value.quantize(FOUR_DP, rounding=ROUND_HALF_UP)


def normalize_invoice_number(value: str) -> str:
    """
    Normalize invoice numbers so formatting variations compare consistently.

    Examples:
        "INV/2026-27/001"  -> "inv2026-27-001"
        "INV-2026-27-001"  -> "inv2026-27-001"
        "inv 2026-27 001"  -> "inv2026-27-001"
        "INV2026-27-001"   -> "inv2026-27-001"
        "10-1" vs "1-01"   -> "10-1" vs "1-01" (kept distinct between numeric runs)
    """
    raw = value.strip().lower()
    tokens = _ALNUM_RUN_REGEX.findall(raw)
    if not tokens:
        return "-".join(raw.split())[:100]
    joined = "-".join(tokens)
    collapsed = _ALPHA_DIGIT_BOUNDARY_REGEX.sub("", joined)
    return collapsed[:100]


def compute_indian_financial_year(invoice_date: date | None) -> str | None:
    """Return Indian April-March financial year label (e.g. '2026-27') for a date."""
    if invoice_date is None:
        return None
    start_year = invoice_date.year if invoice_date.month >= 4 else invoice_date.year - 1
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def determine_invoice_tax_type(
    *,
    cgst_amount: Decimal,
    sgst_amount: Decimal,
    igst_amount: Decimal,
) -> InvoiceTaxType:
    has_intra = cgst_amount > ZERO or sgst_amount > ZERO
    has_inter = igst_amount > ZERO
    if has_intra and has_inter:
        return "MIXED"
    if has_intra:
        return "INTRA_STATE"
    if has_inter:
        return "INTER_STATE"
    return "NO_GST"


def is_valid_indian_gstin(value: str | None) -> bool:
    if not value:
        return False
    return bool(_GSTIN_REGEX.fullmatch(value.strip().upper()))


@dataclass(frozen=True)
class ReconciliationDiscrepancy:
    code: str
    severity: DiscrepancySeverity
    message: str
    details: dict[str, Any] | None = None


@dataclass(frozen=True)
class ResolvedLineItem:
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
    expected_taxable_value: Decimal
    expected_line_total: Decimal


@dataclass(frozen=True)
class ReconciliationResult:
    rounding_tolerance: Decimal
    computed_expected_total: Decimal
    declared_total: Decimal
    variance_amount: Decimal
    reconciliation_status: ReconciliationStatus
    line_items_taxable_sum: Decimal | None
    line_item_variance_amount: Decimal | None
    line_item_reconciliation_status: LineItemReconciliationStatus
    line_item_warning: str | None
    discrepancies: tuple[ReconciliationDiscrepancy, ...]


def resolve_line_item_inputs(
    items: Sequence[InvoiceLineItemInput],
) -> list[ResolvedLineItem]:
    """
    Normalize input line items with fixed-point Decimal math without overriding
    explicit user-entered taxable_value or line_total values.
    """
    resolved: list[ResolvedLineItem] = []
    for idx, item in enumerate(items):
        qty = quantize_qty(item.quantity)
        unit_price = quantize_qty(item.unit_price)
        discount = quantize_money(item.discount_amount)
        gross = quantize_money(qty * unit_price)
        expected_taxable = quantize_money(gross - discount)
        if expected_taxable < ZERO:
            expected_taxable = ZERO

        effective_taxable = (
            quantize_money(item.taxable_value)
            if item.taxable_value is not None
            else expected_taxable
        )

        cgst = quantize_money(item.cgst_amount)
        sgst = quantize_money(item.sgst_amount)
        igst = quantize_money(item.igst_amount)
        cess = quantize_money(item.cess_amount)
        expected_total = quantize_money(effective_taxable + cgst + sgst + igst + cess)
        effective_total = (
            quantize_money(item.line_total)
            if item.line_total is not None
            else expected_total
        )

        resolved.append(
            ResolvedLineItem(
                sort_order=item.sort_order if item.sort_order is not None else idx,
                description=item.description,
                hsn_sac=item.hsn_sac,
                quantity=qty,
                unit=item.unit,
                unit_price=unit_price,
                discount_amount=discount,
                taxable_value=effective_taxable,
                tax_rate_percent=quantize_money(item.tax_rate_percent),
                cgst_amount=cgst,
                sgst_amount=sgst,
                igst_amount=igst,
                cess_amount=cess,
                line_total=effective_total,
                expected_taxable_value=expected_taxable,
                expected_line_total=expected_total,
            )
        )
    return resolved


def resolve_existing_line_items(items: Sequence[Any]) -> list[ResolvedLineItem]:
    """Build ResolvedLineItem snapshots from persisted ORM InvoiceLineItem objects."""
    resolved: list[ResolvedLineItem] = []
    for idx, item in enumerate(items):
        qty = quantize_qty(Decimal(item.quantity))
        unit_price = quantize_qty(Decimal(item.unit_price))
        discount = quantize_money(Decimal(item.discount_amount))
        gross = quantize_money(qty * unit_price)
        expected_taxable = max(ZERO, quantize_money(gross - discount))
        taxable = quantize_money(Decimal(item.taxable_value))
        cgst = quantize_money(Decimal(item.cgst_amount))
        sgst = quantize_money(Decimal(item.sgst_amount))
        igst = quantize_money(Decimal(item.igst_amount))
        cess = quantize_money(Decimal(item.cess_amount))
        line_total = quantize_money(Decimal(item.line_total))
        expected_total = quantize_money(taxable + cgst + sgst + igst + cess)
        resolved.append(
            ResolvedLineItem(
                sort_order=int(getattr(item, "sort_order", idx)),
                description=str(item.description),
                hsn_sac=str(item.hsn_sac),
                quantity=qty,
                unit=str(item.unit),
                unit_price=unit_price,
                discount_amount=discount,
                taxable_value=taxable,
                tax_rate_percent=quantize_money(Decimal(item.tax_rate_percent)),
                cgst_amount=cgst,
                sgst_amount=sgst,
                igst_amount=igst,
                cess_amount=cess,
                line_total=line_total,
                expected_taxable_value=expected_taxable,
                expected_line_total=expected_total,
            )
        )
    return resolved


def reconcile_invoice(
    *,
    taxable_amount: Decimal,
    discount_amount: Decimal,
    discount_mode: DiscountMode | str,
    cgst_amount: Decimal,
    sgst_amount: Decimal,
    igst_amount: Decimal,
    cess_amount: Decimal,
    freight_amount: Decimal,
    other_charges_amount: Decimal,
    round_off_amount: Decimal,
    total_amount: Decimal,
    rounding_tolerance: Decimal | None = None,
    line_items: Sequence[ResolvedLineItem] = (),
    supplier_gstin: str | None = None,
    buyer_gstin: str | None = None,
    place_of_supply_code: str | None = None,
    is_reverse_charge: bool = False,
) -> ReconciliationResult:
    """
    Perform non-destructive Decimal-based GST header & line-item reconciliation.

    Formula:
        effective_discount = discount_amount if discount_mode == "POST_TAX_COMMERCIAL" else 0.00
        computed_expected_total = (
            taxable_amount - effective_discount
            + cgst_amount + sgst_amount + igst_amount + cess_amount
            + freight_amount + other_charges_amount + round_off_amount
        )
        variance_amount = total_amount - computed_expected_total

    Never modifies user-entered invoice totals and never rejects invoices on variance.
    """
    tolerance = quantize_money(
        rounding_tolerance
        if rounding_tolerance is not None
        else DEFAULT_ROUNDING_TOLERANCE
    )
    if tolerance < ZERO:
        tolerance = ZERO

    taxable = quantize_money(taxable_amount)
    discount = quantize_money(discount_amount)
    cgst = quantize_money(cgst_amount)
    sgst = quantize_money(sgst_amount)
    igst = quantize_money(igst_amount)
    cess = quantize_money(cess_amount)
    freight = quantize_money(freight_amount)
    other_charges = quantize_money(other_charges_amount)
    round_off = quantize_money(round_off_amount)
    declared_total = quantize_money(total_amount)

    effective_discount = discount if discount_mode == "POST_TAX_COMMERCIAL" else ZERO
    expected_total = quantize_money(
        taxable
        - effective_discount
        + cgst
        + sgst
        + igst
        + cess
        + freight
        + other_charges
        + round_off
    )
    variance = quantize_money(declared_total - expected_total)

    all_monetary_zero = all(
        amount == ZERO
        for amount in (
            taxable,
            discount,
            cgst,
            sgst,
            igst,
            cess,
            freight,
            other_charges,
            round_off,
            declared_total,
        )
    )

    discrepancies: list[ReconciliationDiscrepancy] = []

    if all_monetary_zero and not line_items:
        reconciliation_status: ReconciliationStatus = "PENDING_INPUT"
    else:
        abs_variance = abs(variance)
        if abs_variance == ZERO:
            reconciliation_status = "MATCHED"
        elif abs_variance <= tolerance:
            reconciliation_status = "WITHIN_ROUNDING_TOLERANCE"
            discrepancies.append(
                ReconciliationDiscrepancy(
                    code="HEADER_ROUNDING_TOLERANCE",
                    severity="INFO",
                    message=(
                        f"Declared total (INR {declared_total:.2f}) differs from computed expected "
                        f"total (INR {expected_total:.2f}) by INR {variance:.2f}, within tolerance "
                        f"(+/- INR {tolerance:.2f})."
                    ),
                    details={
                        "expectedTotal": f"{expected_total:.2f}",
                        "declaredTotal": f"{declared_total:.2f}",
                        "varianceAmount": f"{variance:.2f}",
                        "roundingTolerance": f"{tolerance:.2f}",
                    },
                )
            )
        else:
            reconciliation_status = "VARIANCE_DETECTED"
            discrepancies.append(
                ReconciliationDiscrepancy(
                    code="HEADER_TOTAL_VARIANCE",
                    severity="WARNING",
                    message=(
                        f"Declared total (INR {declared_total:.2f}) differs from computed expected "
                        f"total (INR {expected_total:.2f}) by INR {variance:.2f}."
                    ),
                    details={
                        "expectedTotal": f"{expected_total:.2f}",
                        "declaredTotal": f"{declared_total:.2f}",
                        "varianceAmount": f"{variance:.2f}",
                        "roundingTolerance": f"{tolerance:.2f}",
                    },
                )
            )

    if not line_items:
        line_items_taxable_sum: Decimal | None = None
        line_item_variance_amount: Decimal | None = None
        line_item_reconciliation_status: LineItemReconciliationStatus = "NO_LINE_ITEMS"
        line_item_warning: str | None = None
    else:
        line_items_taxable_sum = quantize_money(
            sum((item.taxable_value for item in line_items), ZERO)
        )
        line_item_variance_amount = quantize_money(taxable - line_items_taxable_sum)
        if abs(line_item_variance_amount) <= tolerance:
            line_item_reconciliation_status = "MATCHED"
            line_item_warning = None
        else:
            line_item_reconciliation_status = "VARIANCE_WARNING"
            line_item_warning = (
                f"Header taxable amount (INR {taxable:.2f}) differs from sum of line-item "
                f"taxable values (INR {line_items_taxable_sum:.2f}) by INR {line_item_variance_amount:.2f}."
            )
            discrepancies.append(
                ReconciliationDiscrepancy(
                    code="LINE_ITEM_TAXABLE_VARIANCE",
                    severity="WARNING",
                    message=line_item_warning,
                    details={
                        "headerTaxableAmount": f"{taxable:.2f}",
                        "lineItemsTaxableSum": f"{line_items_taxable_sum:.2f}",
                        "lineItemVarianceAmount": f"{line_item_variance_amount:.2f}",
                    },
                )
            )

        # Advisory check on individual line-item math (qty * price - discount vs taxable_value, total)
        for item in line_items:
            taxable_diff = quantize_money(
                item.taxable_value - item.expected_taxable_value
            )
            total_diff = quantize_money(item.line_total - item.expected_line_total)
            if abs(taxable_diff) > tolerance or abs(total_diff) > tolerance:
                discrepancies.append(
                    ReconciliationDiscrepancy(
                        code="LINE_ITEM_MATH_VARIANCE",
                        severity="WARNING",
                        message=(
                            f"Line item #{item.sort_order + 1} ('{item.description[:40]}') "
                            "has arithmetic difference between unit pricing/taxes and stored totals."
                        ),
                        details={
                            "sortOrder": item.sort_order,
                            "expectedTaxableValue": f"{item.expected_taxable_value:.2f}",
                            "declaredTaxableValue": f"{item.taxable_value:.2f}",
                            "expectedLineTotal": f"{item.expected_line_total:.2f}",
                            "declaredLineTotal": f"{item.line_total:.2f}",
                        },
                    )
                )

        # Advisory check on sum of line-item taxes vs header GST breakdown when line taxes exist
        li_cgst_sum = quantize_money(sum((i.cgst_amount for i in line_items), ZERO))
        li_sgst_sum = quantize_money(sum((i.sgst_amount for i in line_items), ZERO))
        li_igst_sum = quantize_money(sum((i.igst_amount for i in line_items), ZERO))
        li_cess_sum = quantize_money(sum((i.cess_amount for i in line_items), ZERO))
        if (li_cgst_sum + li_sgst_sum + li_igst_sum + li_cess_sum) > ZERO:
            tax_diffs = {
                "cgstDiff": quantize_money(cgst - li_cgst_sum),
                "sgstDiff": quantize_money(sgst - li_sgst_sum),
                "igstDiff": quantize_money(igst - li_igst_sum),
                "cessDiff": quantize_money(cess - li_cess_sum),
            }
            if any(abs(diff) > tolerance for diff in tax_diffs.values()):
                discrepancies.append(
                    ReconciliationDiscrepancy(
                        code="LINE_ITEM_TAX_SUM_MISMATCH",
                        severity="WARNING",
                        message=(
                            "Header GST component totals do not match the sum of line-item GST amounts."
                        ),
                        details={k: f"{v:.2f}" for k, v in tax_diffs.items()},
                    )
                )

    # Advisory GST regime checks
    has_intra = cgst > ZERO or sgst > ZERO
    has_inter = igst > ZERO
    if has_intra and has_inter:
        discrepancies.append(
            ReconciliationDiscrepancy(
                code="MIXED_TAX_REGIME",
                severity="WARNING",
                message=(
                    "Both intra-state GST (CGST/SGST) and inter-state GST (IGST) are non-zero."
                ),
                details={
                    "cgstAmount": f"{cgst:.2f}",
                    "sgstAmount": f"{sgst:.2f}",
                    "igstAmount": f"{igst:.2f}",
                },
            )
        )

    if has_intra and abs(cgst - sgst) > TWO_DP:
        discrepancies.append(
            ReconciliationDiscrepancy(
                code="CGST_SGST_ASYMMETRY",
                severity="WARNING",
                message=(
                    f"CGST (INR {cgst:.2f}) and SGST (INR {sgst:.2f}) normally match in intra-state GST."
                ),
                details={
                    "cgstAmount": f"{cgst:.2f}",
                    "sgstAmount": f"{sgst:.2f}",
                },
            )
        )

    # State-code vs GST regime advisory check
    cleaned_supplier_gstin = (supplier_gstin or "").strip().upper()
    cleaned_buyer_gstin = (buyer_gstin or "").strip().upper()
    supplier_state = (
        cleaned_supplier_gstin[:2] if is_valid_indian_gstin(cleaned_supplier_gstin) else None
    )
    recipient_state = place_of_supply_code or (
        cleaned_buyer_gstin[:2] if is_valid_indian_gstin(cleaned_buyer_gstin) else None
    )
    if supplier_state and recipient_state and not (has_intra and has_inter):
        if supplier_state == recipient_state and has_inter:
            discrepancies.append(
                ReconciliationDiscrepancy(
                    code="REGIME_STATE_MISMATCH",
                    severity="WARNING",
                    message=(
                        f"Supplier and place-of-supply share state code '{supplier_state}', "
                        "but IGST was recorded instead of CGST+SGST."
                    ),
                    details={
                        "supplierStateCode": supplier_state,
                        "recipientStateCode": recipient_state,
                    },
                )
            )
        elif supplier_state != recipient_state and has_intra:
            discrepancies.append(
                ReconciliationDiscrepancy(
                    code="REGIME_STATE_MISMATCH",
                    severity="WARNING",
                    message=(
                        f"Supplier state code '{supplier_state}' differs from place-of-supply "
                        f"'{recipient_state}', but CGST/SGST was recorded instead of IGST."
                    ),
                    details={
                        "supplierStateCode": supplier_state,
                        "recipientStateCode": recipient_state,
                    },
                )
            )

    if (
        cleaned_supplier_gstin
        and cleaned_supplier_gstin not in {"PENDING-ENTRY", "URD"}
        and not is_valid_indian_gstin(cleaned_supplier_gstin)
    ):
        discrepancies.append(
            ReconciliationDiscrepancy(
                code="SUPPLIER_GSTIN_FORMAT",
                severity="WARNING",
                message="Supplier GSTIN does not match the 15-character Indian GSTIN format.",
            )
        )

    if is_reverse_charge and (cgst + sgst + igst + cess) > ZERO:
        discrepancies.append(
            ReconciliationDiscrepancy(
                code="REVERSE_CHARGE_TAX_CHECK",
                severity="INFO",
                message=(
                    "Reverse charge (RCM) is enabled while GST amounts are non-zero; "
                    "confirm supplier bill vs recipient RCM self-assessment."
                ),
            )
        )

    if abs(round_off) > EXCESSIVE_ROUND_OFF_THRESHOLD:
        discrepancies.append(
            ReconciliationDiscrepancy(
                code="EXCESSIVE_ROUND_OFF",
                severity="WARNING",
                message=(
                    f"Round-off amount (INR {round_off:.2f}) exceeds typical +/- INR 10.00 threshold."
                ),
                details={"roundOffAmount": f"{round_off:.2f}"},
            )
        )

    return ReconciliationResult(
        rounding_tolerance=tolerance,
        computed_expected_total=expected_total,
        declared_total=declared_total,
        variance_amount=variance,
        reconciliation_status=reconciliation_status,
        line_items_taxable_sum=line_items_taxable_sum,
        line_item_variance_amount=line_item_variance_amount,
        line_item_reconciliation_status=line_item_reconciliation_status,
        line_item_warning=line_item_warning,
        discrepancies=tuple(discrepancies),
    )
