from __future__ import annotations

import csv
import io
import json
import uuid
from collections.abc import Callable
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.services.report_service as report_service
from app.models.review import AuditEvent
from app.services.report_service import format_csv_decimal, sanitize_csv_cell
from tests.test_invoices import (  # noqa: F401 - reuse pg fixtures
    _csrf_headers,
    _onboard_to_workspace,
    _register_user,
    db_session,
    make_client,
    pg_settings,
    pg_test_url,
)


# ---------------------------------------------------------------------------
# Offline unit tests: formula-injection neutralization & numeric CSV safety
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("=SUM(A1:A2)", "'=SUM(A1:A2)"),
        ("+CMD|' /C calc'!A0", "'+CMD|' /C calc'!A0"),
        ("-2+3+cmd", "'-2+3+cmd"),
        ("@SUM(1,1)*cmd", "'@SUM(1,1)*cmd"),
        ("\t=1+1", "'\t=1+1"),
        ("\r+1+1", "'\r+1+1"),
        ("\n-1+1", "'\n-1+1"),
        ("   =HYPERLINK(\"http://evil\")", "'   =HYPERLINK(\"http://evil\")"),
        (" \t @SUM(A1)", "' \t @SUM(A1)"),
        ("\x0b+123", "'\x0b+123"),
        ("Acme\x00 Traders", "Acme Traders"),
        ("Normal Supplier Pvt Ltd", "Normal Supplier Pvt Ltd"),
        ("", ""),
        (None, ""),
    ],
)
def test_sanitize_csv_cell_neutralizes_formula_injection(
    raw_value: str | None, expected: str
) -> None:
    assert sanitize_csv_cell(raw_value) == expected


def test_format_csv_decimal_preserves_negative_financial_amounts() -> None:
    assert format_csv_decimal(Decimal("-15.5")) == "-15.50"
    assert format_csv_decimal(Decimal("-0.50")) == "-0.50"
    assert format_csv_decimal(Decimal("11800.00")) == "11800.00"
    assert format_csv_decimal(None) == "0.00"


# ---------------------------------------------------------------------------
# PostgreSQL 16 integration helpers
# ---------------------------------------------------------------------------


def _setup_reports_workspace(make_client: Callable[..., TestClient]):
    admin_client = make_client()
    reviewer_client = make_client()
    uploader_client = make_client()
    viewer_client = make_client()
    foreign_client = make_client()

    uid = uuid.uuid4().hex[:8]
    reg_admin = _register_user(
        admin_client,
        prefix="rep_adm",
        full_name="CA Kavita Iyer",
        org_name=f"Reports Practice {uid}",
    )
    org_id = reg_admin["organization"]["id"]
    ws1_id = reg_admin["workspace"]["workspaceId"]

    ws2_resp = admin_client.post(
        f"/api/v1/organizations/{org_id}/workspaces",
        headers=_csrf_headers(admin_client),
        json={
            "name": "Sibling Client Workspace",
            "workspaceCode": f"REP-SIB-{uid}".upper(),
            "legalEntityName": "Sibling Client Entity Pvt Ltd",
        },
    )
    assert ws2_resp.status_code == 201, ws2_resp.text
    ws2_id = ws2_resp.json()["workspace"]["id"]

    reg_rev = _register_user(reviewer_client, prefix="rep_rev", full_name="CA Rohit Sen")
    reg_upl = _register_user(uploader_client, prefix="rep_upl", full_name="Data Uploader")
    reg_view = _register_user(viewer_client, prefix="rep_view", full_name="Client Viewer")
    reg_for = _register_user(
        foreign_client, prefix="rep_for", org_name=f"Foreign Practice {uid}"
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
        "reg_upl": reg_upl,
        "ws1_id": ws1_id,
        "ws2_id": ws2_id,
        "ws_for_id": reg_for["workspace"]["workspaceId"],
    }


def _create_invoice(client: TestClient, ws_id: str, **overrides: object) -> dict:
    payload: dict[str, object] = {
        "supplierName": "Sahyadri Precision Components",
        "supplierGstin": "27AAACS1234A1Z5",
        "invoiceNumber": f"SPC-{uuid.uuid4().hex[:6].upper()}",
        "invoiceDate": "2026-11-10",
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
# PostgreSQL 16 integration tests: Summary, Monthly Trend, Exceptions, CSV
# ---------------------------------------------------------------------------


def test_reports_summary_monthly_trend_and_exceptions_with_join_safety(
    make_client: Callable[..., TestClient],
) -> None:
    ctx = _setup_reports_workspace(make_client)
    admin_client = ctx["admin_client"]
    reviewer_client = ctx["reviewer_client"]
    uploader_client = ctx["uploader_client"]
    viewer_client = ctx["viewer_client"]
    foreign_client = ctx["foreign_client"]
    ws1_id = ctx["ws1_id"]
    ws2_id = ctx["ws2_id"]
    ws_for_id = ctx["ws_for_id"]

    # Empty workspace baseline
    empty_summary = viewer_client.get(f"/api/v1/workspaces/{ws1_id}/reports/summary")
    assert empty_summary.status_code == 200, empty_summary.text
    es = empty_summary.json()
    assert es["totalInvoices"] == 0
    assert es["totalInvoiceValue"] == "0.00"
    assert es["currency"] == "INR"
    assert es["isStatutoryFilingReport"] is False

    empty_trend = viewer_client.get(f"/api/v1/workspaces/{ws1_id}/reports/monthly-trend")
    assert empty_trend.status_code == 200
    assert empty_trend.json()["buckets"] == []
    assert empty_trend.json()["excludedCount"] == 0

    # Invalid date range -> 422
    assert (
        viewer_client.get(
            f"/api/v1/workspaces/{ws1_id}/reports/summary",
            params={"dateFrom": "2026-11-15", "dateTo": "2026-11-01"},
        ).status_code
        == 422
    )

    # Create diverse invoices:
    # 1. Verified invoice in 2026-08 (10,000 + 1,800 GST = 11,800)
    inv_verified = _create_invoice(
        admin_client,
        ws1_id,
        invoiceNumber="INV-AUG-001",
        invoiceDate="2026-08-12",
        taxableAmount="10000.00",
        cgstAmount="900.00",
        sgstAmount="900.00",
        totalAmount="11800.00",
    )
    assert (
        reviewer_client.post(
            f"/api/v1/workspaces/{ws1_id}/invoices/{inv_verified['id']}/verify",
            headers=_csrf_headers(reviewer_client),
            json={"confirmationNote": "Verified Aug invoice"},
        ).status_code
        == 200
    )

    # 2. Pending invoice with header variance in 2026-11 (20,000 + 3,600 IGST, declared 24,100 -> variance +500.00)
    inv_variance = _create_invoice(
        uploader_client,
        ws1_id,
        invoiceNumber="INV-NOV-VAR",
        supplierName="Deccan Logistics Ltd",
        invoiceDate="2026-11-04",
        taxableAmount="20000.00",
        cgstAmount="0.00",
        sgstAmount="0.00",
        igstAmount="3600.00",
        totalAmount="24100.00",
    )

    # 3. Flagged invoice in 2026-11 with MULTIPLE open flags (must NOT double-count in summary/trend!)
    inv_flagged = _create_invoice(
        admin_client,
        ws1_id,
        invoiceNumber="INV-NOV-FLG",
        supplierName="Kaveri Industrial Corp",
        invoiceDate="2026-11-15",
        taxableAmount="5000.00",
        cgstAmount="450.00",
        sgstAmount="450.00",
        totalAmount="5900.00",
    )
    for cat, reason in (
        ("GSTIN_ISSUE", "Verify GSTIN registration"),
        ("MISSING_PO_GRN", "Attach store GRN slip"),
    ):
        assert (
            reviewer_client.post(
                f"/api/v1/workspaces/{ws1_id}/invoices/{inv_flagged['id']}/flag",
                headers=_csrf_headers(reviewer_client),
                json={"flagCategory": cat, "reasonText": reason},
            ).status_code
            == 200
        )

    # 4. Undated invoice in PENDING_REVIEW (excluded from monthly trend, counted in summary)
    _create_invoice(
        uploader_client,
        ws1_id,
        invoiceNumber="INV-UNDATED",
        invoiceDate=None,
        taxableAmount="1000.00",
        cgstAmount="90.00",
        sgstAmount="90.00",
        totalAmount="1180.00",
    )

    # 5. Soft-deleted invoice (must be excluded from ALL reports)
    inv_deleted = _create_invoice(
        admin_client,
        ws1_id,
        invoiceNumber="INV-DEL-999",
        invoiceDate="2026-11-18",
        taxableAmount="99999.00",
        cgstAmount="0.00",
        sgstAmount="0.00",
        totalAmount="99999.00",
    )
    assert (
        admin_client.delete(
            f"/api/v1/workspaces/{ws1_id}/invoices/{inv_deleted['id']}",
            headers=_csrf_headers(admin_client),
        ).status_code
        == 204
    )

    # 6. Foreign/sibling workspace invoice (must NEVER leak into ws1)
    _create_invoice(
        admin_client,
        ws2_id,
        invoiceNumber="INV-WS2-ONLY",
        invoiceDate="2026-11-10",
        taxableAmount="50000.00",
        cgstAmount="0.00",
        sgstAmount="0.00",
        totalAmount="50000.00",
    )

    # Summary check
    summary_resp = viewer_client.get(f"/api/v1/workspaces/{ws1_id}/reports/summary")
    assert summary_resp.status_code == 200, summary_resp.text
    s = summary_resp.json()
    assert s["totalInvoices"] == 4
    assert s["verifiedCount"] == 1
    assert s["pendingCount"] == 2
    assert s["flaggedCount"] == 1
    assert s["verificationRatePercent"] == 25
    assert s["verifiedValue"] == "11800.00"
    assert s["pendingValue"] == "25280.00"  # 24100 + 1180
    assert s["flaggedValue"] == "5900.00"
    assert s["totalTaxableValue"] == "36000.00"
    assert s["totalCgst"] == "1440.00"
    assert s["totalSgst"] == "1440.00"
    assert s["totalIgst"] == "3600.00"
    assert s["totalGst"] == "6480.00"
    assert s["totalInvoiceValue"] == "42980.00"
    assert s["openFlagCount"] == 2
    assert s["outstandingReviewCount"] == 3
    assert s["varianceInvoiceCount"] == 1

    # Date-filtered summary check (Nov only -> excludes Aug + undated)
    nov_summary = viewer_client.get(
        f"/api/v1/workspaces/{ws1_id}/reports/summary",
        params={"dateFrom": "2026-11-01", "dateTo": "2026-11-30"},
    )
    assert nov_summary.status_code == 200
    ns = nov_summary.json()
    assert ns["totalInvoices"] == 2
    assert ns["totalInvoiceValue"] == "30000.00"

    # Monthly trend check (window=6m spans 2026-06..2026-11, zero-filling empty months!)
    trend_6m = viewer_client.get(
        f"/api/v1/workspaces/{ws1_id}/reports/monthly-trend",
        params={"window": "6m"},
    )
    assert trend_6m.status_code == 200, trend_6m.text
    t6 = trend_6m.json()
    assert t6["excludedCount"] == 1  # undated invoice
    assert [b["monthKey"] for b in t6["buckets"]] == [
        "2026-06",
        "2026-07",
        "2026-08",
        "2026-09",
        "2026-10",
        "2026-11",
    ]
    by_month = {b["monthKey"]: b for b in t6["buckets"]}
    assert by_month["2026-08"]["totalCount"] == 1
    assert by_month["2026-08"]["verifiedCount"] == 1
    assert by_month["2026-08"]["totalValue"] == "11800.00"
    assert by_month["2026-09"]["totalCount"] == 0
    assert by_month["2026-09"]["totalValue"] == "0.00"
    assert by_month["2026-11"]["totalCount"] == 2
    assert by_month["2026-11"]["pendingCount"] == 1
    assert by_month["2026-11"]["flaggedCount"] == 1
    assert by_month["2026-11"]["totalValue"] == "30000.00"

    trend_all = viewer_client.get(
        f"/api/v1/workspaces/{ws1_id}/reports/monthly-trend",
        params={"window": "all"},
    )
    assert trend_all.status_code == 200
    assert [b["monthKey"] for b in trend_all.json()["buckets"]] == [
        "2026-08",
        "2026-09",
        "2026-10",
        "2026-11",
    ]

    # Mixed currency safety check: create USD invoice and verify 409 without ?currency=
    _create_invoice(
        admin_client,
        ws1_id,
        invoiceNumber="INV-USD-1",
        invoiceDate="2026-11-16",
        currency="USD",
        taxableAmount="100.00",
        cgstAmount="0.00",
        sgstAmount="0.00",
        totalAmount="100.00",
    )
    mixed_err = viewer_client.get(f"/api/v1/workspaces/{ws1_id}/reports/summary")
    assert mixed_err.status_code == 409
    assert mixed_err.json()["error"]["code"] == "MIXED_CURRENCY_NOT_SUPPORTED"
    assert mixed_err.json()["error"]["details"]["currencies"] == ["INR", "USD"]

    usd_summary = viewer_client.get(
        f"/api/v1/workspaces/{ws1_id}/reports/summary",
        params={"currency": "USD"},
    )
    assert usd_summary.status_code == 200
    assert usd_summary.json()["currency"] == "USD"
    assert usd_summary.json()["totalInvoiceValue"] == "100.00"

    # Exceptions feed checks: FLAGGED + unresolved variance, pagination, search, filters
    exc_all = viewer_client.get(f"/api/v1/workspaces/{ws1_id}/reports/exceptions")
    assert exc_all.status_code == 200, exc_all.text
    exc_json = exc_all.json()
    assert exc_json["total"] == 2
    assert [item["invoiceNumber"] for item in exc_json["items"]] == [
        "INV-NOV-FLG",
        "INV-NOV-VAR",
    ]
    flagged_item = exc_json["items"][0]
    assert flagged_item["openFlagCount"] == 2
    assert len(flagged_item["openFlags"]) == 2
    assert flagged_item["lastAction"]["actionType"] == "FLAG_INVOICE"
    assert flagged_item["lastAction"]["actorDisplayName"] == "CA Rohit Sen"

    # Filter by flagCategory
    exc_cat = viewer_client.get(
        f"/api/v1/workspaces/{ws1_id}/reports/exceptions",
        params={"flagCategory": "GSTIN_ISSUE"},
    )
    assert exc_cat.status_code == 200
    assert exc_cat.json()["total"] == 1
    assert exc_cat.json()["items"][0]["invoiceNumber"] == "INV-NOV-FLG"

    # Search by supplier name
    exc_search = viewer_client.get(
        f"/api/v1/workspaces/{ws1_id}/reports/exceptions",
        params={"search": "Deccan"},
    )
    assert exc_search.status_code == 200
    assert exc_search.json()["total"] == 1
    assert exc_search.json()["items"][0]["invoiceId"] == inv_variance["id"]

    # Pagination page=2
    exc_p2 = viewer_client.get(
        f"/api/v1/workspaces/{ws1_id}/reports/exceptions",
        params={"page": 2, "pageSize": 1},
    )
    assert exc_p2.status_code == 200
    assert exc_p2.json()["total"] == 2
    assert len(exc_p2.json()["items"]) == 1
    assert exc_p2.json()["items"][0]["invoiceNumber"] == "INV-NOV-VAR"

    # Cross-workspace 404 isolation
    for path in ("summary", "monthly-trend", "exceptions", "export.csv"):
        assert (
            foreign_client.get(f"/api/v1/workspaces/{ws1_id}/reports/{path}").status_code
            == 404
        )
        assert (
            viewer_client.get(f"/api/v1/workspaces/{ws_for_id}/reports/{path}").status_code
            == 404
        )


def test_reports_csv_export_rbac_formula_safety_limits_and_audit(
    make_client: Callable[..., TestClient],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _setup_reports_workspace(make_client)
    admin_client = ctx["admin_client"]
    reviewer_client = ctx["reviewer_client"]
    uploader_client = ctx["uploader_client"]
    viewer_client = ctx["viewer_client"]
    ws1_id = ctx["ws1_id"]

    # Dangerous spreadsheet payloads in text fields + legitimate negative financial values
    danger_inv = _create_invoice(
        admin_client,
        ws1_id,
        supplierName='=CMD|" /C calc"!A0',
        invoiceNumber="+INV-001,2",
        invoiceDate="2026-11-11",
        taxableAmount="1000.00",
        cgstAmount="90.00",
        sgstAmount="90.00",
        roundOffAmount="-0.50",
        totalAmount="1170.00",  # variance = -9.50 (negative!)
        reviewerNote="  @SUM(A1:A9) check\tnote",
    )
    assert (
        reviewer_client.post(
            f"/api/v1/workspaces/{ws1_id}/invoices/{danger_inv['id']}/verify",
            headers=_csrf_headers(reviewer_client),
            json={
                "confirmVarianceAcknowledgment": True,
                "confirmationNote": "-confirmed negative variance -9.50",
            },
        ).status_code
        == 200
    )

    # RBAC: UPLOADER forbidden (403); VIEWER allowed (200)
    upl_export = uploader_client.get(f"/api/v1/workspaces/{ws1_id}/reports/export.csv")
    assert upl_export.status_code == 403
    assert upl_export.json()["error"]["code"] == "FORBIDDEN_ROLE"

    csv_resp = viewer_client.get(f"/api/v1/workspaces/{ws1_id}/reports/export.csv")
    assert csv_resp.status_code == 200, csv_resp.text
    assert csv_resp.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=\"norus-billwise-report-" in csv_resp.headers["content-disposition"]

    parsed_rows = list(csv.reader(io.StringIO(csv_resp.text)))
    assert len(parsed_rows) == 2
    headers = parsed_rows[0]
    row = dict(zip(headers, parsed_rows[1]))

    # Formula payloads neutralized, negative numeric amounts preserved cleanly
    assert row["Invoice Number"] == "'+INV-001,2"
    assert row["Supplier Name"] == "'=CMD|\" /C calc\"!A0"
    assert row["Reviewer Note"] == "'@SUM(A1:A9) check\tnote"
    assert row["Round Off"] == "-0.50"
    assert row["Variance Amount"] == "-9.50"
    assert row["Status"] == "VERIFIED"
    assert row["Verified By"] == "CA Rohit Sen"
    assert row["Verified At"] != ""

    # Audit event emitted for report.csv_exported
    audit_resp = admin_client.get(
        f"/api/v1/workspaces/{ws1_id}/audit-events",
        params={"eventType": "report.csv_exported"},
    )
    assert audit_resp.status_code == 200
    assert audit_resp.json()["total"] == 1
    assert audit_resp.json()["items"][0]["metadata"]["rowCount"] == 1

    # Row limit overflow -> explicit 422 EXPORT_ROW_LIMIT_EXCEEDED (never silent truncation)
    _create_invoice(admin_client, ws1_id, invoiceNumber="SECOND-ROW", invoiceDate="2026-11-12")
    monkeypatch.setattr(report_service, "MAX_CSV_EXPORT_ROWS", 1)
    limit_resp = viewer_client.get(f"/api/v1/workspaces/{ws1_id}/reports/export.csv")
    assert limit_resp.status_code == 422
    assert limit_resp.json()["error"]["code"] == "EXPORT_ROW_LIMIT_EXCEEDED"
    assert limit_resp.json()["error"]["details"] == {"rowCount": 2, "maxRows": 1}


def test_audit_events_filters_pagination_rbac_and_immutability(
    make_client: Callable[..., TestClient],
    db_session: Session,
) -> None:
    ctx = _setup_reports_workspace(make_client)
    admin_client = ctx["admin_client"]
    reviewer_client = ctx["reviewer_client"]
    uploader_client = ctx["uploader_client"]
    viewer_client = ctx["viewer_client"]
    foreign_client = ctx["foreign_client"]
    ws1_id = ctx["ws1_id"]
    ws2_id = ctx["ws2_id"]
    uploader_id = ctx["reg_upl"]["user"]["id"]

    inv_adm = _create_invoice(admin_client, ws1_id, invoiceNumber="AUD-ADM-1")
    inv_upl = _create_invoice(uploader_client, ws1_id, invoiceNumber="AUD-UPL-1")
    assert (
        reviewer_client.post(
            f"/api/v1/workspaces/{ws1_id}/invoices/{inv_adm['id']}/flag",
            headers=_csrf_headers(reviewer_client),
            json={"flagCategory": "CUSTOM", "reasonText": "Audit trail test flag"},
        ).status_code
        == 200
    )

    # Admin/Reviewer/Viewer see all workspace events; UPLOADER sees ONLY own actorUserId events
    adm_audit = admin_client.get(f"/api/v1/workspaces/{ws1_id}/audit-events")
    view_audit = viewer_client.get(f"/api/v1/workspaces/{ws1_id}/audit-events")
    upl_audit = uploader_client.get(f"/api/v1/workspaces/{ws1_id}/audit-events")
    assert adm_audit.status_code == 200
    assert view_audit.status_code == 200
    assert upl_audit.status_code == 200
    assert adm_audit.json()["total"] == view_audit.json()["total"]
    assert adm_audit.json()["total"] > upl_audit.json()["total"]
    assert all(
        item["actorUserId"] == uploader_id for item in upl_audit.json()["items"]
    )

    # Filter by entityType + entityId
    ent_audit = viewer_client.get(
        f"/api/v1/workspaces/{ws1_id}/audit-events",
        params={"entityType": "invoice", "entityId": inv_upl["id"]},
    )
    assert ent_audit.status_code == 200
    assert ent_audit.json()["total"] == 1
    assert ent_audit.json()["items"][0]["eventType"] == "invoice.created"

    # Invalid dateFrom > dateTo -> 422
    assert (
        viewer_client.get(
            f"/api/v1/workspaces/{ws1_id}/audit-events",
            params={
                "dateFrom": "2026-11-20T00:00:00Z",
                "dateTo": "2026-11-01T00:00:00Z",
            },
        ).status_code
        == 422
    )

    # Tied timestamps across audit_events paginate deterministically without duplicates
    tied_ts = datetime(2026, 11, 20, 12, 0, 0, tzinfo=timezone.utc)
    ws_uuid = uuid.UUID(ws1_id)
    events = list(
        db_session.scalars(
            select(AuditEvent).where(AuditEvent.workspace_id == ws_uuid)
        )
    )
    for ev in events:
        ev.created_at = tied_ts
    db_session.commit()

    p1 = viewer_client.get(
        f"/api/v1/workspaces/{ws1_id}/audit-events", params={"page": 1, "pageSize": 2}
    )
    p2 = viewer_client.get(
        f"/api/v1/workspaces/{ws1_id}/audit-events", params={"page": 2, "pageSize": 2}
    )
    assert p1.status_code == 200 and p2.status_code == 200
    p1_ids = [i["id"] for i in p1.json()["items"]]
    p2_ids = [i["id"] for i in p2.json()["items"]]
    assert len(p1_ids) == 2 and len(p2_ids) == 2
    assert set(p1_ids).isdisjoint(set(p2_ids))

    # Redaction & immutability
    serialized = json.dumps(adm_audit.json())
    for secret_key in ("ipAddress", "ip_address", "storageKey", "passwordHash", "refreshToken"):
        assert secret_key not in serialized

    for method in ("POST", "PATCH", "DELETE"):
        res = admin_client.request(
            method,
            f"/api/v1/workspaces/{ws1_id}/audit-events",
            headers=_csrf_headers(admin_client),
            json={},
        )
        assert res.status_code == 405

    # Cross-workspace 404
    assert (
        foreign_client.get(f"/api/v1/workspaces/{ws1_id}/audit-events").status_code == 404
    )
    assert (
        admin_client.get(f"/api/v1/workspaces/{ws2_id}/audit-events").json()["total"]
        < adm_audit.json()["total"]
    )
