# STATUS — Project Progress

**Current Milestone:** Task 002.7 — Reports API, Formula-Safe CSV Export & Frontend Workspace API Integration (built on `main` `7d4783dc`)
**Status:** Verified Remote `main` (`7d4783dcd2824b4dda81815a91674a583f812ba0`, CI #26 `45016892293` green across Frontend + Python 3.12 + PostgreSQL 16); Task 002.7 implemented locally (`npm run lint`, 17 `npm test` tests, `npm run build`, and Python `compileall`/AST Passing; Live `pytest`/PostgreSQL 16 Execution & Live Full-Stack Browser QA `BLOCKED` Locally)

---

## Completed Work in Task 002.7 (`7d4783dc` + Reports & Frontend API Patch)

1. **Backend Reports, Formula-Safe CSV Export & Audit Validation (`backend/app/schemas/reports.py`, `backend/app/services/report_service.py`, `backend/app/api/v1/reports.py`, `backend/app/api/v1/__init__.py`, `backend/app/services/audit_service.py`)**
   - Mounted `/api/v1/workspaces/{workspaceId}/reports/summary`, `/monthly-trend`, `/exceptions`, and `/export.csv`.
   - Implemented single-query SQL `Decimal` summary aggregations (plus separate `OPEN` flag count query to avoid join fan-out double counting), mixed-currency `409 MIXED_CURRENCY_NOT_SUPPORTED` guards, `isStatutoryFilingReport = false` operational disclaimer, PostgreSQL `DATE_TRUNC('month', invoice_date)` chronological zero-filled trends (`excludedCount`, `outOfWindowCount`), and a paginated exceptions feed with batched `OPEN` flags and latest `ReviewAction` snippets (zero N+1).
   - Implemented streaming RFC-4180 CSV export (`yield_per(500)`) with whitespace/control-char-aware formula-injection neutralization (preserving signed negative `Decimal` totals), `MAX_CSV_EXPORT_ROWS = 10_000` (`422 EXPORT_ROW_LIMIT_EXCEEDED`), `Due Date` / `Verified At` / `Verified By` columns, `UPLOADER` `403` restriction, and `report.csv_exported` audit logging.
   - Added `dateFrom <= dateTo` validation (`422`) and deterministic `(created_at DESC, id DESC)` tie-breaking to `audit_service.list_workspace_audit_events`.
2. **Frontend API Client, Auth Gate & Full Workspace Integration (`src/`, `vite.config.ts`, `.env.example`)**
   - Configured Vite `/api` dev proxy (`VITE_API_PROXY_TARGET`, `VITE_API_BASE_URL`) and added `src/services/apiClient.ts` (`credentials: 'include'`, `norus_csrf_token` -> `X-CSRF-Token`, single-flight `401` `/auth/refresh` recovery, typed `ApiClientError`) plus `src/services/apiMappers.ts` aligned to backend canonical `fieldKey`s and `UPLOADER` restrictions.
   - Rebuilt `src/state/WorkspaceContext.tsx` and added `src/components/auth/AuthScreen.tsx` to hydrate real cookie sessions (`/auth/me`), switch workspaces safely with monotonic request sequence + `AbortController` cancellation guards, enforce `requireHumanReview = true`, and isolate `localStorage` strictly to browser UI density preferences (`compactTables`).
   - Wired `Sidebar`, `TopBar`, `UploadInvoiceModal` (`<= 15 MB` multipart upload), `FlagInvoiceModal`, `DocumentPreview` (`CLEAN`-only sandboxed preview with scan-status warning notice), and all 6 SPA pages (`DashboardPage`, `InvoicesPage`, `ReviewCentrePage`, `SuppliersPage`, `ReportsPage`, `SettingsPage`) to live FastAPI endpoints with explicit loading, error, empty, RBAC, variance acknowledgment, flag resolution, reopen, and review-history dialogs.
   - Hardened `src/services/reportService.ts` CSV cell neutralization for leading whitespace/control characters and NUL bytes.
3. **Automated Tests (`backend/tests/test_reports_and_audit.py`, `backend/tests/test_review.py`, `tests/apiClient.test.ts`)**
   - Added offline unit + PostgreSQL 16 integration tests for Reports summary, monthly trends, mixed-currency `409`, exceptions pagination, CSV formula neutralization, row limits, `/audit-events` filters/`UPLOADER` scoping/tied timestamps/`405` immutability, plus the Task 002.6 `test_flagging_verified_invoice_clears_verifier_and_history_page2_tie_breaking` regression test.
   - Added 6 frontend test suites (`tests/apiClient.test.ts`) verifying URL/cookie helpers, error envelopes, CSRF + `credentials: 'include'` + single-flight refresh, single `unauthorizedHandler` invocation, `apiMappers`, whitespace-prefixed CSV neutralization, and request-sequence stale-response protection.

---

## Prior Completed Work on `main` (`7d4783dc` and earlier)

- **Task 002.6 (`bfa17947` → `7d4783dc`):** Human Review Workflow, Exception Flags & Immutable Audit Ledger (`/verify`, `/flag`, `/flags/{flagId}/resolve`, `/reopen`, `/review-history`); verified green on GitHub Actions CI #26 (`45016892293`).
- **Task 002.5A (`606ac011` → `bfa17947`):** Fixed `fieldKey` camelCase normalization and `DRAFT-<8hex>` placeholder duplicate matching (`CI #25` `45015052231` green).
- **Task 002.5 (`389868fa` → `606ac011`):** Dedicated `Decimal` Indian GST & line-item reconciliation engine, advisory duplicate detection, and workspace-scoped Invoices CRUD/search/filter/sort API.
- **Task 002.4H (`b3e04609` → `389868fa`):** Removed obsolete root patch `NORUS-TASK-002-4D.patch` and aligned milestone docs (`CI #23` `45011666003` green).
- **Task 002.4G (`b3e04609`):** Fixed case-sensitive regex assertion in `test_settings_rejects_blank_document_storage_root` (`CI #22` `45010488214` green).
- **Task 002.4D (`a793a7f9` → `f7cd90c4`):** `status.HTTP_413_REQUEST_ENTITY_TOO_LARGE` Starlette compatibility fix and `task-002-4c.patch` removal.
- **Task 002.4C (`1adcbdcd`):** Migration `0003_doc_failed_scan_status`, pure ASGI `RequestIdMiddleware` & `DocumentUploadSizeLimitMiddleware` (`16 MiB`), inline PDF `Content-Security-Policy: sandbox`, and pre-storage NUL validation.
- **Task 002.4B (`e255af40`):** Pluggable `DocumentStorage` + `LocalFilesystemStorage` (UUID keys, canonical path & symlink containment, `15 MB` cap, magic-byte validation, `CLEAN`-only streaming).
- **Task 002.4A (`c0c0b615` + `fa899175a`):** Suppliers Master API (`GET`/`POST`/`PATCH` `/suppliers`, GSTIN/PAN normalization, SQL aggregates, RBAC, CSRF, audit events).
- **Task 002.3 (`125857a` / `a873fcb`):** Auth/session/CSRF/RBAC foundation with Argon2id, `HttpOnly`/`SameSite=Lax` cookies, rotating refresh token families, PostgreSQL rate limiting, and anti-enumeration invitations.
- **Task 001 – 002.2B:** React 19 + TypeScript + Tailwind CSS v4 frontend SPA and FastAPI modular monolith foundation.

---

## Implemented vs. Deferred & MVP-Readiness Boundary

- **Locally Executed & Passing (Container):** React TypeScript lint (`npm run lint`), 17 frontend unit tests (`npm test`), production bundle (`npm run build`), Python bytecode compilation (`python3 -m compileall -q backend/app backend/alembic backend/tests`), and AST import/syntax verification.
- **Locally Blocked:** Live `pytest` execution (including `backend/tests/test_reports_and_audit.py` and `backend/tests/test_review.py`), Alembic migrations against PostgreSQL 16, and live Playwright browser verification against a running FastAPI + PostgreSQL 16 stack remain `BLOCKED` inside this container due to absent Python 3.12, backend pip dependencies, and PostgreSQL 16; must run on a feature branch in GitHub Actions CI and staging before merging or starting Task 002.8.
- **A. Required Next Before Controlled Accounting-Firm Pilot (Task 002.8):**
  - Wire real malware scanning (`ClamAV` async/inline worker) and controlled scan-status transitions (`PENDING -> CLEAN | INFECTED | FAILED`) so uploaded PDFs/images become streamable during pilot review, add upload/stream rate limits, add `S3`/`MinIO` `DocumentStorage` adapter support, configure pilot HTTPS deployment (`COOKIE_SECURE=true`, `CORS_ORIGINS`, `TRUSTED_PROXIES`, persistent storage), and run live Playwright E2E verification against FastAPI + PostgreSQL 16.
- **B. Required Before Production Deployment:**
  - Mandatory ClamAV scanning + quarantine alerting, orphan-blob lifecycle cleanup, workspace storage quotas, automated PostgreSQL backups + PITR restore drills, DBA `SELECT`/`INSERT`-only role grants on `review_actions` and `audit_events`, email verification & password-reset flows, data retention/deletion workflows, and structured monitoring/alerting.
- **C. Later Releases (Post-MVP):**
  - Automated OCR/AI field extraction + bounding-box evidence workers, bulk CSV/ERP export adapters (Tally/Zoho/SAP), and multi-office practice analytics.
