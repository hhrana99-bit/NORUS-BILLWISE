# NEXT_TASK — Exact Next Recommended Development Task

## Baseline & Checkpoint (`389868fa2213389609de8aaa8c5b7e67044ba47a` + Task 002.5)

Remote `main` (`389868fa2213389609de8aaa8c5b7e67044ba47a`) is **100% green** on GitHub Actions (`45011666003`). Task 002.5 (Invoices CRUD, GST/line-item `Decimal` reconciliation engine, advisory duplicate detection, and `test_invoices.py`) is implemented locally and must pass CI (`pytest -v -ra` against PostgreSQL 16) before merging and starting Task 002.6.

---

## Immediate Next Implementation Batch: NORUS BILLWISE TASK 002.6 — Human Review Workflow, Exception Flags & Immutable Audit Ledger

### Objective
Implement the mandatory human-review sign-off endpoints on top of Task 002.5 (`invoices`), ensuring AI/uploader entries can never become `VERIFIED` without authorized human confirmation, unresolved arithmetic/line-item variances require explicit acknowledgment, and every decision writes to `review_actions` and `audit_events`.

### Deliverables

1. **Human Review Endpoints (`backend/app/schemas/review.py`, `backend/app/services/review_service.py`, `backend/app/api/v1/review.py`)**
   - `POST /api/v1/workspaces/{workspaceId}/invoices/{invoiceId}/verify`: `WORKSPACE_ADMIN` and `REVIEWER` only (`UPLOADER` and `VIEWER` forbidden with `403`); rejects unacknowledged header or line-item variance (`409 VARIANCE_ACKNOWLEDGMENT_REQUIRED` unless `confirmVarianceAcknowledgment = true` with non-blank `confirmationNote`); sets `verified_by_user_id` and `verified_at`; resolves compatible open flags when `resolveOpenFlags = true`; records immutable `ReviewAction` and `AuditEvent`.
   - `POST /api/v1/workspaces/{workspaceId}/invoices/{invoiceId}/flag`: `WORKSPACE_ADMIN` and `REVIEWER` only; rejects blank `reasonText` (`422 EMPTY_FLAG_REASON`); creates `InvoiceReviewFlag`, sets `status = "FLAGGED"`, clears prior `verified_by_user_id`/`verified_at` if reopened/flagged, and logs `ReviewAction` + `AuditEvent`.
   - `POST /api/v1/workspaces/{workspaceId}/invoices/{invoiceId}/flags/{flagId}/resolve`: Resolves/dismisses an open flag with mandatory resolution note and optional transition back to `PENDING_REVIEW` when no open flags remain.
   - `POST /api/v1/workspaces/{workspaceId}/invoices/{invoiceId}/reopen`: Reopens a `VERIFIED` or `FLAGGED` invoice to `PENDING_REVIEW` with mandatory reason and immutable `ReviewAction` entry.
   - `GET /api/v1/workspaces/{workspaceId}/invoices/{invoiceId}/review-history`: Returns chronological `actions[]` and `flags[]` for authorized workspace members.
2. **PostgreSQL 16 Integration Tests (`backend/tests/test_review.py`)**
   - Verify variance acknowledgment gating (`409 VARIANCE_ACKNOWLEDGMENT_REQUIRED`), flag creation/resolution lifecycle, reopen unlocking for edits, `UPLOADER`/`VIEWER` `403` enforcement on review actions, CSRF, cross-workspace `404` isolation, and immutable `review_actions` + `audit_events` persistence.

---

## Subsequent Dependency-Ordered Batches Toward Pilot & Production

- **Task 002.7 (Reporting, CSV Export & Frontend API Integration):** Implement `/reports/summary`, `/monthly-trend`, `/exceptions`, formula-safe `/export.csv`, wire React `WorkspaceContext` to FastAPI (`credentials: 'include'` + `X-CSRF-Token`, sign-in/workspace switcher UI, removing mock-only dependency), and run full-stack Playwright + FastAPI verification.
- **Pilot Security & Document Scan Readiness (Task 002.8):** Integrate ClamAV/malware scanning worker + scan-status transition flow (`PENDING -> CLEAN | INFECTED | FAILED`) so uploaded PDFs/images can safely stream in Review Centre, add upload/download rate limits, configure S3/MinIO `DocumentStorage` adapter + pilot HTTPS deployment hardening, and add email verification / password reset before onboarding external firms.
