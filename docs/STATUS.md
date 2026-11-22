# STATUS — Project Progress

**Current Milestone:** Task 002.5A — Invoice Engine Validation, Regression Audit & Stabilization (built on `main` `606ac011`)
**Status:** Verified Remote `main` (`606ac011d2615735f23e8eaa9b086c52935a3f2a`, Task 002.5 already committed); GitHub Actions CI #24 (`45014078164`) passed Frontend and Alembic upgrade but failed in `pytest`; Task 002.5A fixes applied locally (`compileall` + Frontend Passing; Live `pytest`/PostgreSQL 16 Execution `BLOCKED` Locally)

---

## Completed Work in Task 002.5 / 002.5A (`606ac011` + Stabilization Patch)

1. **Dedicated `Decimal` GST & Line-Item Reconciliation Engine (`backend/app/services/reconciliation_service.py`)**
   - Deterministic `Decimal` (`ROUND_HALF_UP`) calculation of `computedExpectedTotal`, `varianceAmount`, `reconciliationStatus` (`PENDING_INPUT`, `MATCHED`, `WITHIN_ROUNDING_TOLERANCE`, `VARIANCE_DETECTED`), `lineItemsTaxableSum`, `lineItemVarianceAmount`, `lineItemReconciliationStatus` (`NO_LINE_ITEMS`, `MATCHED`, `VARIANCE_WARNING`), and structured advisory `discrepancies[]` (`MIXED_TAX_REGIME`, `CGST_SGST_ASYMMETRY`, `REGIME_STATE_MISMATCH`, `LINE_ITEM_MATH_VARIANCE`, `LINE_ITEM_TAX_SUM_MISMATCH`, `REVERSE_CHARGE_TAX_CHECK`, `SUPPLIER_GSTIN_FORMAT`, `EXCESSIVE_ROUND_OFF`).
   - Shared `normalize_invoice_number` formatter invariance (`INV/2026-27/001` == `inv-2026-27-001` while keeping `10-1` != `1-01`) reused by `document_service.py`, plus Indian April–March financial year helpers.
2. **Workspace-Scoped Invoices API & Advisory Duplicate Detection (`backend/app/schemas/invoices.py`, `backend/app/services/invoice_service.py`, `backend/app/api/v1/invoices.py`)**
   - Implemented `GET /invoices` (escaped LIKE search, filters including `taxType`, `reconciliationStatus`, `lineItemReconciliationStatus`, `financialYear`, `dateFrom`..`dateTo`, sorting, pagination, zero N+1 query overhead), `POST /invoices` (always starts `PENDING_REVIEW`, `extra="forbid"`), `GET /invoices/{invoiceId}`, `PATCH /invoices/{invoiceId}` (`FOR UPDATE`, `VERIFIED` lock `409 VERIFIED_INVOICE_LOCKED`, `UPLOADER` `PENDING_REVIEW`-only restriction), and `DELETE /invoices/{invoiceId}` (`WORKSPACE_ADMIN` soft-delete on unverified invoices preserving child line items, flags, review actions, and audit logs).
   - Validated workspace ownership (`404` on cross-workspace `supplierId`/`documentId`) and document scan gating (`409 DOCUMENT_INFECTED` / `409 DOCUMENT_SCAN_FAILED`).
   - Implemented advisory duplicate warnings scoped to active workspace invoices (`NORMALIZED_INVOICE_NUMBER` within same Indian FY/180 days; `SIMILAR_TOTAL_WITHIN_45_DAYS` within `±₹0.01`), respecting `WorkspaceSettings.enable_duplicate_warnings`.
3. **Task 002.5A Audit & CI Failure Fixes (`backend/app/schemas/invoices.py`, `backend/app/services/invoice_service.py`, `backend/tests/test_invoices.py`)**
   - Fixed `InvoiceFieldVerificationInput.validate_field_key` to accept both `camelCase` (`totalAmount`, `cgst`, `sgst`, `igst`, etc.) and canonical `snake_case` (`total_amount`, `cgst_amount`, etc.) field keys and normalize to canonical DB `field_key` values (preventing HTTP `422` failures in `test_invoices.py` PATCH/RBAC tests).
   - Fixed `detect_advisory_duplicates` zero-total draft exclusion so `DRAFT-<8hex>` UUID prefixes starting with `0-9` (normalized to `draft<8hex>` without hyphen) are excluded consistently alongside `draft-*`.
   - Added unit test assertions in `backend/tests/test_invoices.py` for camelCase/snake_case `fieldKey` normalization and duplicate-alias detection.

---

## Prior Completed Work on `main` (`606ac011` and earlier)

- **Task 002.5 (`389868fa` → `606ac011`):** Invoices CRUD, `Decimal` GST reconciliation, advisory duplicate detection, and `test_invoices.py` merged onto `main` (Frontend CI green; Backend pytest step failed in CI #24 `45014078164`).
- **Task 002.4H (`b3e04609` → `389868fa`):** Removed obsolete root patch `NORUS-TASK-002-4D.patch`, aligned milestone docs, and confirmed CI `45011666003` green on `main`.
- **Task 002.4G (`b3e04609`):** Fixed case-sensitive regex assertion in `test_settings_rejects_blank_document_storage_root` (`CI #22` `45010488214` green).
- **Task 002.4D (`a793a7f9` → `f7cd90c4`):** `status.HTTP_413_REQUEST_ENTITY_TOO_LARGE` Starlette compatibility fix in `backend/app/main.py` and `backend/app/services/storage_service.py`, plus `task-002-4c.patch` removal.
- **Task 002.4C (`1adcbdcd`):** Migration `0003_doc_failed_scan_status` (`FAILED` scan status), pure ASGI `RequestIdMiddleware` & `DocumentUploadSizeLimitMiddleware` (`16 MiB` pre-multipart limit), inline PDF `Content-Security-Policy: sandbox`, and pre-storage `\x00` NUL-byte validation on `supplierName`/`invoiceNumber`.
- **Task 002.4B (`e255af40`):** Pluggable `DocumentStorage` + `LocalFilesystemStorage` (UUID keys, canonical path & symlink containment, `15 MB` streaming cap, magic-byte validation, optional draft invoice staging, `CLEAN`-only content streaming).
- **Task 002.4A (`c0c0b615` + `fa89175a`):** Suppliers Master API (`GET`/`POST`/`PATCH` `/suppliers`, GSTIN/PAN whitespace trimming before max-length validation, `FOR UPDATE` + `IntegrityError` handling, SQL invoice aggregates, RBAC, CSRF, audit events).
- **Task 002.3 (`125857a` / `a873fcb`):** Auth/session/CSRF/RBAC foundation with Argon2id, `HttpOnly`/`SameSite=Lax` cookies, rotating refresh token families, PostgreSQL rate limiting, and anti-enumeration invitations.
- **Task 001 – 002.2B:** React 19 + TypeScript + Tailwind CSS v4 frontend SPA and FastAPI modular monolith foundation.

---

## Implemented vs. Deferred & MVP-Readiness Boundary

- **Locally Executed & Passing (Container):** Python bytecode compilation (`python3 -m compileall -q backend/app backend/alembic backend/tests`) and React frontend (`npm run lint`, `npm test`, `npm run build`).
- **Locally Blocked:** Live `pytest` execution (including `backend/tests/test_invoices.py`) and PostgreSQL 16 migration/integration verification remain `BLOCKED` inside this container due to absent Python 3.12, backend dependencies, and PostgreSQL 16; must run on a feature branch in GitHub Actions CI before starting Task 002.6.
- **A. Required Before Controlled Accounting-Firm Pilot:**
  - **Task 002.6 (After Green Task 002.5 CI):** Human Review workflow endpoints (`/verify`, `/flag`, `/flags/{flagId}/resolve`, `/reopen`, `/review-history`, mandatory variance acknowledgment, immutable `review_actions` & `audit_events`).
  - **Task 002.7:** Backend Reports API (`/summary`, `/monthly-trend`, `/exceptions`, `/export.csv`) and Frontend `WorkspaceContext` API integration (`credentials: 'include'` + `X-CSRF-Token`, auth/workspace UI).
  - **Document Scan & Pilot Storage Readiness:** Wire real malware scanning (e.g., ClamAV async/inline worker) or a controlled non-production `CLEAN` transition gate so uploaded PDFs/images become streamable during pilot review, plus pilot HTTPS deployment config (`COOKIE_SECURE=true`, production `CORS_ORIGINS`, `TRUSTED_PROXIES`, persistent volume/object storage).
- **B. Required Before Production Deployment:**
  - Encrypted S3/MinIO `DocumentStorage` adapter + lifecycle orphan-blob cleanup, mandatory ClamAV malware scanning pipeline, upload/stream rate limits & workspace storage quotas, automated PostgreSQL backups + PITR restore drills, email verification & password-reset flows, data retention/deletion workflows, and structured monitoring/alerting.
- **C. Later Releases (Post-MVP):**
  - Automated OCR/AI field extraction + bounding-box evidence workers, bulk CSV/ERP export adapters (Tally/Zoho/SAP), and multi-office practice analytics.
