# NEXT_TASK — Exact Next Recommended Development Task

## Baseline & Checkpoint (`bfa179475c087eb5d7f7d305b6b69a5f481c96b3` + Task 002.6)

Remote `main` (`bfa179475c087eb5d7f7d305b6b69a5f481c96b3`) passed GitHub Actions CI run #25 (`45015052231`) completely across Frontend (Node 22) and Backend (Python 3.12 + PostgreSQL 16). Task 002.6 implements the Human Review Workflow, Exception Flags & Immutable Audit Ledger (`/verify`, `/flag`, `/flags/{flagId}/resolve`, `/reopen`, `/review-history`), plus `test_review.py` and the Task 002.5 `test_invoices.py` draft-placeholder duplicate regression test. Apply `NORUS-TASK-002-6.patch` on a dedicated feature branch and verify full green GitHub Actions CI (`pytest -v -ra` against PostgreSQL 16) before merging and starting Task 002.7.

---

## Immediate Next Implementation Batch: NORUS BILLWISE TASK 002.7 — Backend Reports, Formula-Safe CSV Export & Frontend API Integration

### Objective
Deliver the workspace reporting/export endpoints and connect the React SPA (`src/state/WorkspaceContext.tsx` and pages) to the FastAPI backend via cookie credentials + CSRF headers so accounting teams can run an end-to-end verified workflow against PostgreSQL 16.

### Deliverables

1. **Backend Reports & Audit Endpoints (`backend/app/schemas/reports.py`, `backend/app/services/report_service.py`, `backend/app/api/v1/reports.py`)**
   - `GET /api/v1/workspaces/{workspaceId}/reports/summary`: Live workspace KPIs and `Decimal` GST sums excluding soft-deleted invoices (`deleted_at IS NULL`), optionally filtered by `dateFrom`..`dateTo`.
   - `GET /api/v1/workspaces/{workspaceId}/reports/monthly-trend`: Chronological zero-filled monthly counts and totals (`window=6m|12m|all`) derived via SQL from `invoice_date`.
   - `GET /api/v1/workspaces/{workspaceId}/reports/exceptions`: Active `FLAGGED`, `VARIANCE_DETECTED`, and `VARIANCE_WARNING` exception list.
   - `GET /api/v1/workspaces/{workspaceId}/reports/export.csv`: RFC-4180 CSV register export (`WORKSPACE_ADMIN`, `REVIEWER`, `VIEWER` only) with server-side CSV formula-injection neutralization and `audit_events` logging.
   - `GET /api/v1/workspaces/{workspaceId}/audit-events`: Paginated workspace audit feed (with `UPLOADER` scoped to own actions).
2. **Frontend API Client & `WorkspaceContext` Integration (`src/`)**
   - Add typed cookie + `X-CSRF-Token` HTTP client (`credentials: 'include'`), sign-in/session hydration (`/auth/login`, `/auth/me`, `/auth/refresh`, `/auth/logout`), and wire Invoices, Suppliers, Documents, Review Centre (`/verify`, `/flag`, `/flags/{flagId}/resolve`, `/reopen`, `/review-history`), Settings, and Reports to FastAPI without altering the human-review gate or `Decimal`-string presentation.
3. **Full-Stack Verification**
   - PostgreSQL 16 `pytest` coverage for Reports, CSV formula neutralization, and Audit Events, plus Playwright end-to-end verification against live FastAPI + React build.

---

## Subsequent Batch Toward Controlled Pilot & Production

- **Task 002.8 (Document Malware Scanning, Object Storage & Production Auth Hardening):** Wire ClamAV malware scanning pipeline (`PENDING -> CLEAN | INFECTED | FAILED`) so uploaded PDFs/images become streamable during pilot review, add upload/stream rate limits, add encrypted `S3`/`MinIO` `DocumentStorage` adapter + orphan-blob cleanup, and implement email verification + password-reset flows before external customer onboarding.
