from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.services.review_service as review_service
from app.core.config import Settings, get_settings
from app.core.cookies import CSRF_COOKIE_NAME
from app.main import create_app
from app.models.accounting import Invoice
from app.models.review import InvoiceReviewFlag, ReviewAction
from app.models.tenancy import utc_now
from app.schemas.review import (
    FlagInvoiceRequest,
    ReopenInvoiceRequest,
    ResolveFlagRequest,
    ReviewActionDto,
    ReviewAuditEventDto,
    VerifyInvoiceRequest,
)
from tests.test_invoices import (  # noqa: F401 - reuse pg_test_url, pg_settings, db_session, make_client fixtures
    _csrf_headers,
    _onboard_to_workspace,
    _register_user,
    db_session,
    make_client,
    pg_settings,
    pg_test_url,
)


# ---------------------------------------------------------------------------
# Offline unit tests: review schemas, extra='forbid', validation markers & DTOs
# ---------------------------------------------------------------------------


def test_review_schemas_enforce_strict_fields_and_serialize_cleanly() -> None:
    # VerifyInvoiceRequest rejects server-managed fields, duplicates, and NUL bytes
    for forbidden in (
        {"status": "VERIFIED"},
        {"verifiedByUserId": str(uuid.uuid4())},
        {"verifiedAt": utc_now().isoformat()},
        {"workspaceId": str(uuid.uuid4())},
    ):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            VerifyInvoiceRequest.model_validate(forbidden)

    with pytest.raises(ValidationError, match="Duplicate fieldKey"):
        VerifyInvoiceRequest.model_validate(
            {
                "fieldVerifications": [
                    {"fieldKey": "totalAmount", "status": "VERIFIED"},
                    {"fieldKey": "total_amount", "status": "VERIFIED"},
                ]
            }
        )

    with pytest.raises(ValidationError, match="NUL"):
        VerifyInvoiceRequest.model_validate({"confirmationNote": "Bad\x00note"})

    # FlagInvoiceRequest checks
    with pytest.raises(ValidationError, match="EMPTY_FLAG_REASON"):
        FlagInvoiceRequest.model_validate({"flagCategory": "CUSTOM", "reasonText": "   "})

    with pytest.raises(ValidationError):
        FlagInvoiceRequest.model_validate({"flagCategory": "UNKNOWN_CAT", "reasonText": "Issue"})

    with pytest.raises(ValidationError, match="Unsupported fieldKey"):
        FlagInvoiceRequest.model_validate({"reasonText": "Check", "fieldKey": "nonExistentField"})

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        FlagInvoiceRequest.model_validate({"reasonText": "Mismatch", "status": "OPEN"})

    flag_req = FlagInvoiceRequest.model_validate(
        {"flagCategory": "ARITHMETIC_MISMATCH", "reasonText": "  CGST   mismatch  ", "fieldKey": "cgst"}
    )
    assert flag_req.reason_text == "CGST mismatch"
    assert flag_req.field_key == "cgst_amount"

    # ResolveFlagRequest checks
    with pytest.raises(ValidationError, match="INVALID_FLAG_RESOLUTION"):
        ResolveFlagRequest.model_validate({"resolutionStatus": "RESOLVED", "resolutionNote": "  "})

    with pytest.raises(ValidationError):
        ResolveFlagRequest.model_validate({"resolutionStatus": "OPEN", "resolutionNote": "Still open"})

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ResolveFlagRequest.model_validate(
            {"resolutionNote": "Fixed", "resolvedByUserId": str(uuid.uuid4())}
        )

    # ReopenInvoiceRequest checks
    with pytest.raises(ValidationError, match="REOPEN_REASON_REQUIRED"):
        ReopenInvoiceRequest.model_validate({"reason": "   "})

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ReopenInvoiceRequest.model_validate({"reason": "Credit note", "status": "PENDING_REVIEW"})

    # Fixed 2-decimal varianceAmountAtAction & omitted IP address in audit DTO
    action_dto = ReviewActionDto(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        invoice_id=uuid.uuid4(),
        actor_user_id=uuid.uuid4(),
        actor_display_name="CA Reviewer",
        action_type="VERIFY_WITH_VARIANCE",
        previous_status="PENDING_REVIEW",
        new_status="VERIFIED",
        variance_acknowledged=True,
        variance_amount_at_action=Decimal("1000.5"),
        comment="Confirmed surcharge",
        field_changes={"resolvedFlagIds": []},
        created_at=utc_now(),
    )
    dumped_action = action_dto.model_dump(by_alias=True)
    assert dumped_action["varianceAmountAtAction"] == "1000.50"

    assert "ip_address" not in ReviewAuditEventDto.model_fields
    assert "ipAddress" not in ReviewAuditEventDto.model_fields


# ---------------------------------------------------------------------------
# PostgreSQL 16 integration helpers
# ---------------------------------------------------------------------------


def _setup_review_workspace(make_client: Callable[..., TestClient]):
    admin_client = make_client()
    reviewer_client = make_client()
    uploader_client = make_client()
    viewer_client = make_client()
    foreign_client = make_client()

    uid = uuid.uuid4().hex[:8]
    reg_admin = _register_user(
        admin_client,
        prefix="rev_adm",
        full_name="CA Meera Nair",
        org_name=f"Review Practice {uid}",
    )
    org_id = reg_admin["organization"]["id"]
    ws1_id = reg_admin["workspace"]["workspaceId"]

    ws2_resp = admin_client.post(
        f"/api/v1/organizations/{org_id}/workspaces",
        headers=_csrf_headers(admin_client),
        json={
            "name": "Sibling Review Client",
            "workspaceCode": f"REV-SIB-{uid}".upper(),
            "legalEntityName": "Sibling Review Entity Pvt Ltd",
        },
    )
    assert ws2_resp.status_code == 201, ws2_resp.text
    ws2_id = ws2_resp.json()["workspace"]["id"]

    reg_rev = _register_user(reviewer_client, prefix="rev_rev", full_name="CA Arjun Rao")
    reg_upl = _register_user(uploader_client, prefix="rev_upl", full_name="Article Clerk")
    reg_view = _register_user(viewer_client, prefix="rev_view", full_name="Audit Partner Viewer")
    reg_for = _register_user(
        foreign_client, prefix="rev_for", org_name=f"Foreign Practice {uid}"
    )

    _onboard_to_workspace(
        admin_client,
        org_id=org_id,
        workspace_id=ws1_id,
        member_client=reviewer_client,
        member_email=reg_rev["user"]["email"],
        workspace_role="REVIEWER",
    )
    _onboard_to_workspace(
        admin_client,
        org_id=org_id,
        workspace_id=ws1_id,
        member_client=uploader_client,
        member_email=reg_upl["user"]["email"],
        workspace_role="UPLOADER",
    )
    _onboard_to_workspace(
        admin_client,
        org_id=org_id,
        workspace_id=ws1_id,
        member_client=viewer_client,
        member_email=reg_view["user"]["email"],
        workspace_role="VIEWER",
    )

    return {
        "admin_client": admin_client,
        "reviewer_client": reviewer_client,
        "uploader_client": uploader_client,
        "viewer_client": viewer_client,
        "foreign_client": foreign_client,
        "reg_admin": reg_admin,
        "reg_rev": reg_rev,
        "ws1_id": ws1_id,
        "ws2_id": ws2_id,
        "ws_for_id": reg_for["workspace"]["workspaceId"],
    }


def _create_invoice(
    client: TestClient,
    ws_id: str,
    **overrides: object,
) -> dict:
    payload: dict[str, object] = {
        "supplierName": "Bharat Precision Tools Pvt Ltd",
        "supplierGstin": "27AAACB1234F1Z5",
        "invoiceNumber": f"BPT-{uuid.uuid4().hex[:6].upper()}",
        "invoiceDate": "2026-11-05",
        "taxableAmount": "10000.00",
        "cgstAmount": "900.00",
        "sgstAmount": "900.00",
        "totalAmount": "11800.00",
    }
    payload.update(overrides)
    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/invoices",
        headers=_csrf_headers(client),
        json=payload,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# PostgreSQL 16 integration tests: Verification gate, variances, flags, reopen, history
# ---------------------------------------------------------------------------


def test_review_verify_workflow_mandatory_fields_variances_and_flags(
    make_client: Callable[..., TestClient],
    db_session: Session,
) -> None:
    ctx = _setup_review_workspace(make_client)
    admin_client = ctx["admin_client"]
    reviewer_client = ctx["reviewer_client"]
    uploader_client = ctx["uploader_client"]
    viewer_client = ctx["viewer_client"]
    foreign_client = ctx["foreign_client"]
    ws1_id = ctx["ws1_id"]
    ws2_id = ctx["ws2_id"]
    ws_for_id = ctx["ws_for_id"]
    reviewer_id = ctx["reg_rev"]["user"]["id"]

    # 1. Draft with placeholder fields is rejected cleanly until completed
    draft_inv = _create_invoice(
        uploader_client,
        ws1_id,
        supplierName="Pending Extraction",
        invoiceNumber=f"DRAFT-{uuid.uuid4().hex[:8].upper()}",
        invoiceDate=None,
        taxableAmount="0.00",
        cgstAmount="0.00",
        sgstAmount="0.00",
        totalAmount="0.00",
    )
    missing_resp = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{draft_inv['id']}/verify",
        headers=_csrf_headers(reviewer_client),
        json={},
    )
    assert missing_resp.status_code == 409, missing_resp.text
    assert missing_resp.json()["error"]["code"] == "MISSING_REQUIRED_FIELD_VERIFICATION"
    assert set(missing_resp.json()["error"]["details"]["missingFields"]) == {
        "supplierName",
        "invoiceNumber",
        "invoiceDate",
        "totalAmount",
    }

    # 2. Balanced invoice with tracked fieldVerifications needing sign-off
    bal_inv = _create_invoice(
        admin_client,
        ws1_id,
        fieldVerifications=[
            {"fieldKey": "totalAmount", "status": "NEEDS_REVIEW", "sourcePage": 1}
        ],
    )
    bal_id = bal_inv["id"]

    # UPLOADER & VIEWER forbidden on /verify
    for unauthorized in (uploader_client, viewer_client):
        r = unauthorized.post(
            f"/api/v1/workspaces/{ws1_id}/invoices/{bal_id}/verify",
            headers=_csrf_headers(unauthorized),
            json={},
        )
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "FORBIDDEN_ROLE"

    # Tampered server fields rejected (422)
    tamper = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{bal_id}/verify",
        headers=_csrf_headers(reviewer_client),
        json={"verifiedByUserId": reviewer_id, "status": "VERIFIED"},
    )
    assert tamper.status_code == 422

    # Unverified tracked field blocks verification
    unverif = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{bal_id}/verify",
        headers=_csrf_headers(reviewer_client),
        json={},
    )
    assert unverif.status_code == 409
    assert unverif.json()["error"]["code"] == "MISSING_REQUIRED_FIELD_VERIFICATION"
    assert unverif.json()["error"]["details"]["unverifiedFields"] == ["totalAmount"]

    # Submitting non-VERIFIED status in verify fieldVerifications -> 422
    bad_fv_verify = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{bal_id}/verify",
        headers=_csrf_headers(reviewer_client),
        json={
            "fieldVerifications": [
                {"fieldKey": "totalAmount", "status": "NEEDS_REVIEW"}
            ]
        },
    )
    assert bad_fv_verify.status_code == 422
    assert bad_fv_verify.json()["error"]["code"] == "INVALID_FIELD_VERIFICATION_STATUS"

    # Reviewer verifies balanced invoice and confirms tracked field in one atomic call
    verify_ok = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{bal_id}/verify",
        headers=_csrf_headers(reviewer_client),
        json={
            "confirmationNote": "All GST lines match PDF copy.",
            "fieldVerifications": [
                {"fieldKey": "totalAmount", "status": "VERIFIED", "sourcePage": 1}
            ],
        },
    )
    assert verify_ok.status_code == 200, verify_ok.text
    verified_json = verify_ok.json()
    assert verified_json["status"] == "VERIFIED"
    assert verified_json["verifiedByUserId"] == reviewer_id
    assert verified_json["verifiedAt"] is not None
    assert verified_json["fieldVerifications"][0]["status"] == "VERIFIED"

    # Re-verifying already VERIFIED invoice -> 409 INVOICE_ALREADY_VERIFIED
    reverify = admin_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{bal_id}/verify",
        headers=_csrf_headers(admin_client),
        json={},
    )
    assert reverify.status_code == 409
    assert reverify.json()["error"]["code"] == "INVOICE_ALREADY_VERIFIED"

    # 3. Header variance requires explicit human acknowledgment + non-blank note
    var_inv = _create_invoice(
        admin_client,
        ws1_id,
        taxableAmount="50000.00",
        cgstAmount="4500.00",
        sgstAmount="4500.00",
        totalAmount="60000.00",  # +1000.00 header variance
    )
    var_id = var_inv["id"]

    blocked_var = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{var_id}/verify",
        headers=_csrf_headers(reviewer_client),
        json={},
    )
    assert blocked_var.status_code == 409, blocked_var.text
    assert blocked_var.json()["error"]["code"] == "VARIANCE_ACKNOWLEDGMENT_REQUIRED"
    assert blocked_var.json()["error"]["details"]["varianceAmount"] == "1000.00"

    blank_note_var = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{var_id}/verify",
        headers=_csrf_headers(reviewer_client),
        json={"confirmVarianceAcknowledgment": True, "confirmationNote": "   "},
    )
    assert blank_note_var.status_code == 409
    assert blank_note_var.json()["error"]["code"] == "VARIANCE_ACKNOWLEDGMENT_REQUIRED"

    ack_var = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{var_id}/verify",
        headers=_csrf_headers(reviewer_client),
        json={
            "confirmVarianceAcknowledgment": True,
            "confirmationNote": "Confirmed INR 1,000.00 un-itemized pallet charge on physical bill.",
        },
    )
    assert ack_var.status_code == 200, ack_var.text
    assert ack_var.json()["status"] == "VERIFIED"

    # 4. Line-item taxable variance (even with 0 header variance) ALSO requires explicit acknowledgment
    li_var_inv = _create_invoice(
        admin_client,
        ws1_id,
        taxableAmount="10000.00",
        cgstAmount="900.00",
        sgstAmount="900.00",
        totalAmount="11800.00",
        lineItems=[{"description": "Machining", "quantity": "1", "unitPrice": "9500.00"}],
    )
    assert li_var_inv["lineItemReconciliationStatus"] == "VARIANCE_WARNING"
    li_blocked = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{li_var_inv['id']}/verify",
        headers=_csrf_headers(reviewer_client),
        json={},
    )
    assert li_blocked.status_code == 409
    assert li_blocked.json()["error"]["code"] == "VARIANCE_ACKNOWLEDGMENT_REQUIRED"
    assert li_blocked.json()["error"]["details"]["lineItemVarianceAmount"] == "500.00"

    li_ack = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{li_var_inv['id']}/verify",
        headers=_csrf_headers(reviewer_client),
        json={
            "confirmVarianceAcknowledgment": True,
            "confirmationNote": "Packing fee omitted from itemized lines.",
        },
    )
    assert li_ack.status_code == 200

    # 5. Open flags block verify unless resolveOpenFlags=True with valid note
    flagged_inv = _create_invoice(admin_client, ws1_id)
    flagged_id = flagged_inv["id"]
    flag_resp = admin_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{flagged_id}/flag",
        headers=_csrf_headers(admin_client),
        json={"flagCategory": "GSTIN_ISSUE", "reasonText": "Check GSTIN state suffix"},
    )
    assert flag_resp.status_code == 200, flag_resp.text
    assert flag_resp.json()["status"] == "FLAGGED"

    open_flag_blocked = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{flagged_id}/verify",
        headers=_csrf_headers(reviewer_client),
        json={},
    )
    assert open_flag_blocked.status_code == 409
    assert open_flag_blocked.json()["error"]["code"] == "UNRESOLVED_REVIEW_FLAGS"

    # Explicit blank flagResolutionNote must fail 422 even if confirmationNote is provided
    blank_flag_note = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{flagged_id}/verify",
        headers=_csrf_headers(reviewer_client),
        json={
            "resolveOpenFlags": True,
            "flagResolutionNote": "   ",
            "confirmationNote": "Looks good",
        },
    )
    assert blank_flag_note.status_code == 422
    assert blank_flag_note.json()["error"]["code"] == "INVALID_FLAG_RESOLUTION"

    no_flag_note = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{flagged_id}/verify",
        headers=_csrf_headers(reviewer_client),
        json={"resolveOpenFlags": True},
    )
    assert no_flag_note.status_code == 422
    assert no_flag_note.json()["error"]["code"] == "INVALID_FLAG_RESOLUTION"

    resolve_and_verify = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{flagged_id}/verify",
        headers=_csrf_headers(reviewer_client),
        json={
            "resolveOpenFlags": True,
            "flagResolutionNote": "Verified GSTIN 27 against portal printout.",
            "confirmationNote": "Verified after GSTIN check.",
        },
    )
    assert resolve_and_verify.status_code == 200, resolve_and_verify.text
    resolved_json = resolve_and_verify.json()
    assert resolved_json["status"] == "VERIFIED"
    assert resolved_json["openFlagCount"] == 0
    assert resolved_json["reviewFlags"][0]["status"] == "RESOLVED"

    # 6. Cross-workspace 404 isolation & soft-deleted 404
    assert (
        admin_client.post(
            f"/api/v1/workspaces/{ws2_id}/invoices/{bal_id}/verify",
            headers=_csrf_headers(admin_client),
            json={},
        ).status_code
        == 404
    )
    assert (
        foreign_client.post(
            f"/api/v1/workspaces/{ws_for_id}/invoices/{bal_id}/verify",
            headers=_csrf_headers(foreign_client),
            json={},
        ).status_code
        == 404
    )

    del_inv = _create_invoice(admin_client, ws1_id)
    assert (
        admin_client.delete(
            f"/api/v1/workspaces/{ws1_id}/invoices/{del_inv['id']}",
            headers=_csrf_headers(admin_client),
        ).status_code
        == 204
    )
    assert (
        reviewer_client.post(
            f"/api/v1/workspaces/{ws1_id}/invoices/{del_inv['id']}/verify",
            headers=_csrf_headers(reviewer_client),
            json={},
        ).status_code
        == 404
    )

    # Confirm VERIFY_WITH_VARIANCE and audit events persisted in PostgreSQL
    var_actions = list(
        db_session.scalars(
            select(ReviewAction).where(ReviewAction.invoice_id == uuid.UUID(var_id))
        )
    )
    assert len(var_actions) == 1
    assert var_actions[0].action_type == "VERIFY_WITH_VARIANCE"
    assert var_actions[0].variance_acknowledged is True
    assert var_actions[0].variance_amount_at_action == Decimal("1000.00")


def test_review_flag_resolve_reopen_and_immutable_history(
    make_client: Callable[..., TestClient],
    db_session: Session,
) -> None:
    ctx = _setup_review_workspace(make_client)
    admin_client = ctx["admin_client"]
    reviewer_client = ctx["reviewer_client"]
    uploader_client = ctx["uploader_client"]
    viewer_client = ctx["viewer_client"]
    foreign_client = ctx["foreign_client"]
    ws1_id = ctx["ws1_id"]
    ws2_id = ctx["ws2_id"]
    ws_for_id = ctx["ws_for_id"]

    inv = _create_invoice(admin_client, ws1_id)
    inv_id = inv["id"]

    # Validation errors on blank inputs
    empty_flag = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}/flag",
        headers=_csrf_headers(reviewer_client),
        json={"flagCategory": "CUSTOM", "reasonText": "   "},
    )
    assert empty_flag.status_code == 422
    assert empty_flag.json()["error"]["code"] == "EMPTY_FLAG_REASON"

    # RBAC: UPLOADER & VIEWER blocked from flag/resolve/reopen
    for unauthorized in (uploader_client, viewer_client):
        assert (
            unauthorized.post(
                f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}/flag",
                headers=_csrf_headers(unauthorized),
                json={"flagCategory": "CUSTOM", "reasonText": "Denied"},
            ).status_code
            == 403
        )
        assert (
            unauthorized.post(
                f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}/reopen",
                headers=_csrf_headers(unauthorized),
                json={"reason": "Denied"},
            ).status_code
            == 403
        )

    # Create 2 open flags (one with fieldKey)
    f1_resp = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}/flag",
        headers=_csrf_headers(reviewer_client),
        json={
            "flagCategory": "FIELD_DISCREPANCY",
            "reasonText": "Invoice total digit blurry on scan",
            "fieldKey": "totalAmount",
        },
    )
    assert f1_resp.status_code == 200, f1_resp.text
    f1_id = f1_resp.json()["reviewFlags"][0]["id"]
    assert f1_resp.json()["status"] == "FLAGGED"
    assert f1_resp.json()["openFlagCount"] == 1
    assert any(
        fv["fieldKey"] == "total_amount" and fv["status"] == "FLAGGED"
        for fv in f1_resp.json()["fieldVerifications"]
    )

    f2_resp = admin_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}/flag",
        headers=_csrf_headers(admin_client),
        json={
            "flagCategory": "MISSING_PO_GRN",
            "reasonText": "Need stores GRN slip before approval",
        },
    )
    assert f2_resp.status_code == 200
    assert f2_resp.json()["openFlagCount"] == 2
    f2_id = [f["id"] for f in f2_resp.json()["reviewFlags"] if f["id"] != f1_id][0]

    # Unauthorized role cannot resolve flag
    assert (
        uploader_client.post(
            f"/api/v1/workspaces/{ws1_id}/flags/{f1_id}/resolve",
            headers=_csrf_headers(uploader_client),
            json={"resolutionStatus": "DISMISSED", "resolutionNote": "Not allowed"},
        ).status_code
        == 403
    )

    # Blank resolution note -> 422 INVALID_FLAG_RESOLUTION
    bad_res = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/flags/{f1_id}/resolve",
        headers=_csrf_headers(reviewer_client),
        json={"resolutionStatus": "RESOLVED", "resolutionNote": "   "},
    )
    assert bad_res.status_code == 422
    assert bad_res.json()["error"]["code"] == "INVALID_FLAG_RESOLUTION"

    # Cross-workspace flag resolve -> 404
    assert (
        admin_client.post(
            f"/api/v1/workspaces/{ws2_id}/flags/{f1_id}/resolve",
            headers=_csrf_headers(admin_client),
            json={"resolutionStatus": "RESOLVED", "resolutionNote": "Wrong workspace"},
        ).status_code
        == 404
    )
    assert (
        foreign_client.post(
            f"/api/v1/workspaces/{ws_for_id}/flags/{f1_id}/resolve",
            headers=_csrf_headers(foreign_client),
            json={"resolutionStatus": "RESOLVED", "resolutionNote": "Foreign"},
        ).status_code
        == 404
    )

    # Resolve Flag 1 as DISMISSED -> Flag 2 still OPEN so status remains FLAGGED
    res1 = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/flags/{f1_id}/resolve",
        headers=_csrf_headers(reviewer_client),
        json={
            "resolutionStatus": "DISMISSED",
            "resolutionNote": "Confirmed PDF zoom shows 11800.00 clearly.",
            "reopenToPending": True,
        },
    )
    assert res1.status_code == 200, res1.text
    assert res1.json()["flag"]["status"] == "DISMISSED"
    assert res1.json()["invoiceStatus"] == "FLAGGED"
    assert res1.json()["openFlagCount"] == 1

    # Re-resolving Flag 1 -> 409 FLAG_ALREADY_RESOLVED
    dup_res = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/flags/{f1_id}/resolve",
        headers=_csrf_headers(reviewer_client),
        json={"resolutionStatus": "RESOLVED", "resolutionNote": "Duplicate resolve"},
    )
    assert dup_res.status_code == 409
    assert dup_res.json()["error"]["code"] == "FLAG_ALREADY_RESOLVED"

    # Cannot reopen FLAGGED invoice while Flag 2 is still OPEN
    blocked_reopen = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}/reopen",
        headers=_csrf_headers(reviewer_client),
        json={"reason": "Want to bypass open flag"},
    )
    assert blocked_reopen.status_code == 409
    assert blocked_reopen.json()["error"]["code"] == "UNRESOLVED_REVIEW_FLAGS"

    # Resolve Flag 2 with reopenToPending=False -> stays FLAGGED with openFlagCount=0
    res2 = admin_client.post(
        f"/api/v1/workspaces/{ws1_id}/flags/{f2_id}/resolve",
        headers=_csrf_headers(admin_client),
        json={
            "resolutionStatus": "RESOLVED",
            "resolutionNote": "GRN-442 attached to voucher folder.",
            "reopenToPending": False,
        },
    )
    assert res2.status_code == 200
    assert res2.json()["flag"]["status"] == "RESOLVED"
    assert res2.json()["openFlagCount"] == 0
    assert res2.json()["invoiceStatus"] == "FLAGGED"

    # Blank reopen reason -> 422 REOPEN_REASON_REQUIRED
    blank_reopen = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}/reopen",
        headers=_csrf_headers(reviewer_client),
        json={"reason": "   "},
    )
    assert blank_reopen.status_code == 422
    assert blank_reopen.json()["error"]["code"] == "REOPEN_REASON_REQUIRED"

    # Reopen flag-cleared FLAGGED invoice -> PENDING_REVIEW
    reopen_from_flagged = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}/reopen",
        headers=_csrf_headers(reviewer_client),
        json={"reason": "All flags cleared; returning to pending queue."},
    )
    assert reopen_from_flagged.status_code == 200
    assert reopen_from_flagged.json()["status"] == "PENDING_REVIEW"

    # Reopen already PENDING_REVIEW -> 409 INVALID_INVOICE_STATE_TRANSITION
    reopen_pending = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}/reopen",
        headers=_csrf_headers(reviewer_client),
        json={"reason": "Already pending"},
    )
    assert reopen_pending.status_code == 409
    assert reopen_pending.json()["error"]["code"] == "INVALID_INVOICE_STATE_TRANSITION"

    # Re-flag & resolve with reopenToPending=True -> auto-transitions back to PENDING_REVIEW
    f3_resp = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}/flag",
        headers=_csrf_headers(reviewer_client),
        json={"flagCategory": "CUSTOM", "reasonText": "Double-check HSN code"},
    )
    f3_id = [f["id"] for f in f3_resp.json()["reviewFlags"] if f["status"] == "OPEN"][0]
    res3 = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/flags/{f3_id}/resolve",
        headers=_csrf_headers(reviewer_client),
        json={
            "resolutionStatus": "RESOLVED",
            "resolutionNote": "HSN confirmed.",
            "reopenToPending": True,
        },
    )
    assert res3.status_code == 200
    assert res3.json()["invoiceStatus"] == "PENDING_REVIEW"

    # Field totalAmount was FLAGGED earlier; verify blocks until fieldVerification is set VERIFIED
    blocked_fv = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}/verify",
        headers=_csrf_headers(reviewer_client),
        json={},
    )
    assert blocked_fv.status_code == 409
    assert blocked_fv.json()["error"]["code"] == "MISSING_REQUIRED_FIELD_VERIFICATION"

    # Verify with re-verified totalAmount
    verify_1 = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}/verify",
        headers=_csrf_headers(reviewer_client),
        json={
            "confirmationNote": "Initial human approval.",
            "fieldVerifications": [{"fieldKey": "totalAmount", "status": "VERIFIED"}],
        },
    )
    assert verify_1.status_code == 200
    assert verify_1.json()["status"] == "VERIFIED"

    # Locked while VERIFIED
    assert (
        reviewer_client.patch(
            f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}",
            headers=_csrf_headers(reviewer_client),
            json={"reviewerNote": "Blocked while verified"},
        ).status_code
        == 409
    )

    # Reopen VERIFIED invoice -> PENDING_REVIEW, preserves resolved flags, unlocks PATCH, allows re-verify
    reopen_verified = admin_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}/reopen",
        headers=_csrf_headers(admin_client),
        json={"reason": "Supplier issued revised GST credit adjustment"},
    )
    assert reopen_verified.status_code == 200, reopen_verified.text
    rv_json = reopen_verified.json()
    assert rv_json["status"] == "PENDING_REVIEW"
    assert rv_json["verifiedByUserId"] is None
    assert rv_json["verifiedAt"] is None
    assert len(rv_json["reviewFlags"]) == 3

    patch_after_reopen = reviewer_client.patch(
        f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}",
        headers=_csrf_headers(reviewer_client),
        json={"reviewerNote": "Updated note after credit adjustment"},
    )
    assert patch_after_reopen.status_code == 200

    verify_2 = reviewer_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}/verify",
        headers=_csrf_headers(reviewer_client),
        json={"confirmationNote": "Re-verified after adjustment."},
    )
    assert verify_2.status_code == 200

    # History endpoint checks: all roles allowed, asc vs desc ordering, pagination, zero sensitive fields
    for reader in (admin_client, reviewer_client, uploader_client, viewer_client):
        r = reader.get(f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}/review-history")
        assert r.status_code == 200

    hist_asc = reviewer_client.get(
        f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}/review-history",
        params={"order": "asc", "page": 1, "pageSize": 20},
    )
    assert hist_asc.status_code == 200
    h_json = hist_asc.json()
    action_types = [a["actionType"] for a in h_json["actions"]]
    assert action_types == [
        "FLAG_INVOICE",
        "FLAG_INVOICE",
        "RESOLVE_FLAG",
        "RESOLVE_FLAG",
        "REOPEN_PENDING",
        "FLAG_INVOICE",
        "RESOLVE_FLAG",
        "MARK_VERIFIED",
        "REOPEN_PENDING",
        "SAVE_EDITS",
        "MARK_VERIFIED",
    ]
    assert h_json["totalActions"] == 11
    assert h_json["totalFlags"] == 3
    assert len(h_json["auditEvents"]) >= 11

    hist_desc = reviewer_client.get(
        f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}/review-history",
        params={"order": "desc", "page": 1, "pageSize": 5},
    )
    assert hist_desc.status_code == 200
    d_json = hist_desc.json()
    assert len(d_json["actions"]) == 5
    assert d_json["actions"][0]["id"] == h_json["actions"][-1]["id"]

    # Ensure zero sensitive fields leaked anywhere in review-history JSON
    serialized = json.dumps(h_json)
    for forbidden_key in ("ipAddress", "ip_address", "storageKey", "passwordHash", "inviteToken"):
        assert forbidden_key not in serialized

    # History is strictly immutable (PATCH/DELETE -> 405 Method Not Allowed)
    assert (
        admin_client.patch(
            f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}/review-history",
            headers=_csrf_headers(admin_client),
            json={},
        ).status_code
        == 405
    )
    assert (
        admin_client.delete(
            f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}/review-history",
            headers=_csrf_headers(admin_client),
        ).status_code
        == 405
    )

    # Cross-workspace review-history -> 404
    assert (
        admin_client.get(
            f"/api/v1/workspaces/{ws2_id}/invoices/{inv_id}/review-history"
        ).status_code
        == 404
    )
    assert (
        foreign_client.get(
            f"/api/v1/workspaces/{ws_for_id}/invoices/{inv_id}/review-history"
        ).status_code
        == 404
    )

    # Reopen again and soft-delete: review-history remains readable in workspace for audit traceability
    assert (
        admin_client.post(
            f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}/reopen",
            headers=_csrf_headers(admin_client),
            json={"reason": "Withdrawn duplicate supplier copy"},
        ).status_code
        == 200
    )
    assert (
        admin_client.request(
            "DELETE",
            f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}",
            headers=_csrf_headers(admin_client),
            json={"deletionReason": "Withdrawn duplicate supplier copy"},
        ).status_code
        == 204
    )
    hist_after_delete = viewer_client.get(
        f"/api/v1/workspaces/{ws1_id}/invoices/{inv_id}/review-history"
    )
    assert hist_after_delete.status_code == 200
    assert hist_after_delete.json()["totalFlags"] == 3
    assert hist_after_delete.json()["totalActions"] == 12
    assert any(
        evt["eventType"] == "invoice.soft_deleted"
        for evt in hist_after_delete.json()["auditEvents"]
    )
    db_session.expire_all()


def test_review_atomic_rollback_csrf_and_concurrency(
    make_client: Callable[..., TestClient],
    pg_settings: Settings,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _setup_review_workspace(make_client)
    admin_client = ctx["admin_client"]
    reviewer_client = ctx["reviewer_client"]
    ws1_id = ctx["ws1_id"]

    # 1. CSRF required on all 4 mutating review endpoints
    inv_csrf = _create_invoice(admin_client, ws1_id)
    csrf_flag = admin_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{inv_csrf['id']}/flag",
        headers=_csrf_headers(admin_client),
        json={"flagCategory": "CUSTOM", "reasonText": "CSRF check flag"},
    )
    assert csrf_flag.status_code == 200
    csrf_flag_id = csrf_flag.json()["reviewFlags"][0]["id"]

    for method_path in (
        f"/api/v1/workspaces/{ws1_id}/invoices/{inv_csrf['id']}/verify",
        f"/api/v1/workspaces/{ws1_id}/invoices/{inv_csrf['id']}/flag",
        f"/api/v1/workspaces/{ws1_id}/flags/{csrf_flag_id}/resolve",
        f"/api/v1/workspaces/{ws1_id}/invoices/{inv_csrf['id']}/reopen",
    ):
        no_csrf = reviewer_client.post(method_path, json={"reason": "No CSRF"})
        assert no_csrf.status_code == 403
        assert no_csrf.json()["error"]["code"] == "CSRF_TOKEN_INVALID"

    # 2. Atomic rollback when audit event emission fails inside verify_invoice & flag_invoice
    fail_client_admin = make_client(raise_server_exceptions=False)
    for name, value in admin_client.cookies.items():
        fail_client_admin.cookies.set(name, value)
    csrf_hdrs = {
        "X-CSRF-Token": admin_client.cookies.get(CSRF_COOKIE_NAME) or "",
    }

    rollback_inv = _create_invoice(admin_client, ws1_id)
    rollback_uuid = uuid.UUID(rollback_inv["id"])

    def _boom(*args, **kwargs):
        raise RuntimeError("Simulated audit write failure")

    monkeypatch.setattr(review_service, "record_audit_event", _boom)

    resp_verify_err = fail_client_admin.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{rollback_inv['id']}/verify",
        headers=csrf_hdrs,
        json={},
    )
    assert resp_verify_err.status_code == 500

    resp_flag_err = fail_client_admin.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{rollback_inv['id']}/flag",
        headers=csrf_hdrs,
        json={"flagCategory": "CUSTOM", "reasonText": "Should roll back"},
    )
    assert resp_flag_err.status_code == 500

    monkeypatch.undo()

    db_session.expire_all()
    inv_row = db_session.get(Invoice, rollback_uuid)
    assert inv_row is not None
    assert inv_row.status == "PENDING_REVIEW"
    assert inv_row.verified_by_user_id is None
    assert (
        list(
            db_session.scalars(
                select(ReviewAction).where(ReviewAction.invoice_id == rollback_uuid)
            )
        )
        == []
    )
    assert (
        list(
            db_session.scalars(
                select(InvoiceReviewFlag).where(
                    InvoiceReviewFlag.invoice_id == rollback_uuid
                )
            )
        )
        == []
    )

    admin_cookies = dict(admin_client.cookies)
    reviewer_cookies = dict(reviewer_client.cookies)

    def _run_request(
        method: str,
        cookies: dict[str, str],
        barrier: threading.Barrier,
        path: str,
        body: dict,
    ):
        get_settings.cache_clear()
        thread_app = create_app(pg_settings)
        with TestClient(thread_app, base_url="http://testserver") as c:
            c.cookies.update(cookies)
            csrf = cookies[CSRF_COOKIE_NAME]
            barrier.wait(timeout=5)
            return c.request(
                method,
                path,
                headers={"X-CSRF-Token": csrf},
                json=body,
            )

    # 3. Concurrent /verify race -> [200, 409 INVOICE_ALREADY_VERIFIED]
    race_verify_inv = _create_invoice(admin_client, ws1_id)
    barrier_verify = threading.Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_a = pool.submit(
            _run_request,
            "POST",
            admin_cookies,
            barrier_verify,
            f"/api/v1/workspaces/{ws1_id}/invoices/{race_verify_inv['id']}/verify",
            {"confirmationNote": "Admin race"},
        )
        f_b = pool.submit(
            _run_request,
            "POST",
            reviewer_cookies,
            barrier_verify,
            f"/api/v1/workspaces/{ws1_id}/invoices/{race_verify_inv['id']}/verify",
            {"confirmationNote": "Reviewer race"},
        )
        verify_codes = sorted([f_a.result().status_code, f_b.result().status_code])
    assert verify_codes == [200, 409]

    # 4. Concurrent /flags/{flagId}/resolve race -> [200, 409 FLAG_ALREADY_RESOLVED]
    race_flag_inv = _create_invoice(admin_client, ws1_id)
    rf = admin_client.post(
        f"/api/v1/workspaces/{ws1_id}/invoices/{race_flag_inv['id']}/flag",
        headers=_csrf_headers(admin_client),
        json={"flagCategory": "CUSTOM", "reasonText": "Concurrent resolve target"},
    ).json()
    rf_id = rf["reviewFlags"][0]["id"]
    barrier_resolve = threading.Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        r_a = pool.submit(
            _run_request,
            "POST",
            admin_cookies,
            barrier_resolve,
            f"/api/v1/workspaces/{ws1_id}/flags/{rf_id}/resolve",
            {"resolutionStatus": "RESOLVED", "resolutionNote": "Resolved by admin"},
        )
        r_b = pool.submit(
            _run_request,
            "POST",
            reviewer_cookies,
            barrier_resolve,
            f"/api/v1/workspaces/{ws1_id}/flags/{rf_id}/resolve",
            {"resolutionStatus": "DISMISSED", "resolutionNote": "Dismissed by reviewer"},
        )
        resolve_codes = sorted([r_a.result().status_code, r_b.result().status_code])
    assert resolve_codes == [200, 409]

    # 5. Concurrent /flag vs /verify race -> clean FOR UPDATE serialization, no deadlock
    race_fv_inv = _create_invoice(admin_client, ws1_id)
    barrier_fv = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        fv_flag = pool.submit(
            _run_request,
            "POST",
            admin_cookies,
            barrier_fv,
            f"/api/v1/workspaces/{ws1_id}/invoices/{race_fv_inv['id']}/flag",
            {"flagCategory": "CUSTOM", "reasonText": "Race flag"},
        )
        fv_ver = pool.submit(
            _run_request,
            "POST",
            reviewer_cookies,
            barrier_fv,
            f"/api/v1/workspaces/{ws1_id}/invoices/{race_fv_inv['id']}/verify",
            {"confirmationNote": "Race verify"},
        )
        flag_res = fv_flag.result()
        ver_res = fv_ver.result()

    assert flag_res.status_code == 200
    assert ver_res.status_code in {200, 409}

    db_session.expire_all()
    final_fv = db_session.get(Invoice, uuid.UUID(race_fv_inv["id"]))
    assert final_fv is not None
    if ver_res.status_code == 409:
        assert ver_res.json()["error"]["code"] == "UNRESOLVED_REVIEW_FLAGS"
    assert final_fv.status == "FLAGGED"
    assert final_fv.verified_by_user_id is None

    # 6. Concurrent /reopen vs PATCH on VERIFIED invoice -> serializes cleanly without deadlock
    race_reopen_inv = _create_invoice(admin_client, ws1_id)
    assert (
        admin_client.post(
            f"/api/v1/workspaces/{ws1_id}/invoices/{race_reopen_inv['id']}/verify",
            headers=_csrf_headers(admin_client),
            json={},
        ).status_code
        == 200
    )
    barrier_ro = threading.Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        ro_fut = pool.submit(
            _run_request,
            "POST",
            admin_cookies,
            barrier_ro,
            f"/api/v1/workspaces/{ws1_id}/invoices/{race_reopen_inv['id']}/reopen",
            {"reason": "Concurrent reopen"},
        )
        pa_fut = pool.submit(
            _run_request,
            "PATCH",
            reviewer_cookies,
            barrier_ro,
            f"/api/v1/workspaces/{ws1_id}/invoices/{race_reopen_inv['id']}",
            {"reviewerNote": "Concurrent edit"},
        )
        ro_res = ro_fut.result()
        pa_res = pa_fut.result()

    assert ro_res.status_code == 200
    assert pa_res.status_code in {200, 409}
    if pa_res.status_code == 409:
        assert pa_res.json()["error"]["code"] == "VERIFIED_INVOICE_LOCKED"
