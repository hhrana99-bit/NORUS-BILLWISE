# STATUS — Project Progress

**Current Milestone:** Task 002.6 — Human Review Workflow, Exception Flags & Immutable Audit Ledger (built on `main` `bfa17947`)
**Status:** Verified Remote `main` (`bfa179475c087eb5d7f7d305b6b69a5f481c96b3`, CI #25 `45015052231` green across Frontend + Python 3.12 + PostgreSQL 16); Task 002.6 implemented locally (`compileall` + Frontend Passing; Live `pytest`/PostgreSQL 16 Execution `BLOCKED` Locally)

---

## Completed Work in Task 002.6 (`bfa17947` + Human Review Patch)

1. **Human Review Schemas & Validation Error Mapping (`backend/app/schemas/review.py`, `backend/app/schemas/invoices.py`, `backend/app/core/errors.py`)**
   - Added strict `ApiModel` (`extra="forbid"`) payloads `VerifyInvoiceRequest`, `FlagInvoiceRequest`, `ResolveFlagRequest`, and `ReopenInvoiceRequest`, rejecting server-managed fields (`status`, `verifiedByUserId`, `verifiedAt`, `workspaceId`) and mapping blank validation markers to contract codes (`EMPTY_FLAG_REASON`, `INVALID_FLAG_RESOLUTION`, `REOPEN_REASON_REQUIRED`).
   - Added `InvoiceReviewFlagDto` (wired into `InvoiceDetailDto.reviewFlags`), `ResolveFlagResponse`, `ReviewActionDto` (fixed 2-decimal `varianceAmountAtAction`), sanitized `ReviewAuditEventDto` (omitting `ipAddress`), and `ReviewHistoryResponse`; extracted shared `canonicalize_field_key` in `schemas/invoices.py`.
2. **Human Review Service & Mandatory Sign-Off Gate (`backend/app/services/review_service.py`, `backend/app/services/invoice_service.py`)**
   - Implemented `verify_invoice`, `flag_invoice`, `resolve_review_flag`, `reopen_invoice`, and `get_invoice_review_history` using PostgreSQL `SELECT ... FOR UPDATE` with canonical `Invoice -> InvoiceReviewFlag` lock ordering across all endpoints to prevent deadlocks.
   - Enforced mandatory human verification (`WORKSPACE_ADMIN`, `REVIEWER` only), mandatory header and tracked `fieldVerifications` completeness (`409 MISSING_REQUIRED_FIELD_VERIFICATION`), explicit `409 VARIANCE_ACKNOWLEDGMENT_REQUIRED` when header or line-item reconciliation variances exist without acknowledgment + non-blank note, open-flag verification gating (`409 UNRESOLVED_REVIEW_FLAGS` or atomic `resolveOpenFlags` resolution), and `HUMAN_REVIEW_CANNOT_BE_DISABLED` guardrails.
   - Added immutable `ReviewAction(actionType="SAVE_EDITS")` logging inside `invoice_service.update_invoice`, preserved resolved flags/actions/audit logs across reopens and soft deletes, and kept `review-history` strictly read-only and chronologically paginated.
3. **Human Review Router & Automated Tests (`backend/app/api/v1/review.py`, `backend/app/api/v1/invoices.py`, `backend/app/api/v1/__init__.py`, `backend/tests/test_review.py`, `backend/tests/test_invoices.py`)**
   - Mounted all 5 `/workspaces/{workspaceId}/...` review routes (`POST .../verify`, `POST .../flag`, `POST .../flags/{flagId}/resolve`, `POST .../reopen`, `GET .../review-history`) with `require_csrf` on every mutation and strict RBAC + `404` tenant isolation.
   - Confirmed no Alembic schema migration is needed (existing migrations `0001`–`0003` already enforce `invoice_review_flags`, `review_actions`, `audit_events`, and composite RESTRICT foreign keys).
   - Added comprehensive offline unit and PostgreSQL 16 integration/concurrency tests in `backend/tests/test_review.py` plus the Task 002.5 zero-total draft-placeholder non-collision PostgreSQL regression test in `backend/tests/test_invoices.py`.

---

## Prior Completed Work on `main` (`bfa17947` and earlier)

- **Task 002.5A (`606ac011` → `bfa17947`):** Fixed `fieldKey` camelCase normalization and `DRAFT-<8hex>` placeholder duplicate matching; verified completely green on GitHub Actions CI #25 (`45015052231`).
- **Task 002.5 (`389868fa` → `606ac011`):** Dedicated `Decimal` Indian GST & line-item reconciliation engine, advisory duplicate detection, and workspace-scoped Invoices CRUD/search/filter/sort API.
- **Task 002.4H (`b3e04609` → `389868fa`):** Removed obsolete root patch `NORUS-TASK-002-4D.patch` and aligned milestone docs (`CI #23` `45011666003` green).
- **Task 002.4G (`b3e04609`):** Fixed case-sensitive regex assertion in `test_settings_rejects_blank_document_storage_root` (`CI #22` `45010488214` green).
- **Task 002.4D (`a793a7f9` → `f7cd90c4`):** `status.HTTP_413_REQUEST_ENTITY_TOO_LARGE` Starlette compatibility fix and `task-002-4c.patch` removal.
- **Task 002.4C (`1adcbdcd`):** Migration `0003_doc_failed_scan_status`, pure ASGI `RequestIdMiddleware` & `DocumentUploadSizeLimitMiddleware` (`16 MiB`), inline PDF `Content-Security-Policy: sandbox`, and pre-storage NUL validation.
- **Task 002.4B (`e255af40`):** Pluggable `DocumentStorage` + `LocalFilesystemStorage` (UUID keys, canonical path & symlink containment, `15 MB` cap, magic-byte validation, `CLEAN`-only streaming).
- **Task 002.4A (`c0c0b615` + `fa89175a`):** Suppliers Master API (`GET`/`POST`/`PATCH` `/suppliers`, GSTIN/PAN normalization, SQL aggregates, RBAC, CSRF, audit events).
- **Task 002.3 (`125857a` / `a873fcb`):** Auth/session/CSRF/RBAC foundation with Argon2id, `HttpOnly`/`SameSite=Lax` cookies, rotating refresh token families, PostgreSQL rate limiting, and anti-enumeration invitations.
- **Task 001 – 002.2B:** React 19 + TypeScript + Tailwind CSS v4 frontend SPA and FastAPI modular monolith foundation.

---

## Implemented vs. Deferred & MVP-Readiness Boundary

- **Locally Executed & Passing (Container):** Python bytecode compilation (`python3 -m compileall -q backend/app backend/alembic backend/tests`), AST unused-import check, and React frontend (`npm run lint`, `npm test`, `npm run build`).
- **Locally Blocked:** Live `pytest` execution (including `backend/tests/test_review.py` and `backend/tests/test_invoices.py`) and PostgreSQL 16 integration/concurrency verification remain `BLOCKED` inside this container due to absent Python 3.12, backend dependencies, and PostgreSQL 16; must run on a feature branch in GitHub Actions CI before merging or starting Task 002.7.
- **A. Required Before Controlled Accounting-Firm Pilot:**
  - **Task 002.7 (After Green Task 002.6 CI):** Backend Reports & CSV Export API (`/reports/summary`, `/monthly-trend`, `/exceptions`, `/export.csv` with formula neutralization) and Frontend `WorkspaceContext` API integration (`credentials: 'include'` + `X-CSRF-Token`, sign-in/workspace switcher UI, end-to-end Playwright + FastAPI verification).
  - **Task 002.8 (Document Scan & Pilot Storage Readiness):** Wire real malware scanning (e.g., ClamAV async/inline worker) or controlled scan transition flow (`PENDING -> CLEAN | INFECTED | FAILED`) so uploaded PDFs/images become streamable during pilot review, plus pilot HTTPS deployment config (`COOKIE_SECURE=true`, production `CORS_ORIGINS`, `TRUSTED_PROXIES`, persistent volume/object storage).
- **B. Required Before Production Deployment:**
  - Encrypted S3/MinIO `DocumentStorage` adapter + lifecycle orphan-blob cleanup, mandatory ClamAV malware scanning pipeline, upload/stream rate limits & workspace storage quotas, automated PostgreSQL backups + PITR restore drills, email verification & password-reset flows, data retention/deletion workflows, and structured monitoring/alerting.
- **C. Later Releases (Post-MVP):**
  - Automated OCR/AI field extraction + bounding-box evidence workers, bulk CSV/ERP export adapters (Tally/Zoho/SAP), and multi-office practice analytics.
