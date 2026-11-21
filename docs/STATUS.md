# STATUS — Project Progress

**Current Milestone:** Task 002.4C — CI Stabilization & Document Upload Hardening  
**Status:** Task 002.4C Changes Implemented Locally (on top of verified GitHub `main` commit `fa89175a09404f4a1cedfa9a2a296da2b25c1553`, whose CI #17 run `44800309064` passed Frontend CI and failed Backend Step 9; `pytest`, Alembic, and PostgreSQL 16 execution of Task 002.4C pending external Python 3.12+ / GitHub Actions CI run)

---

## Completed Work in Task 002.4C — CI Stabilization & Document Upload Hardening

1. **Filename Sanitization Test Repair (`backend/tests/test_documents.py`)**
   - Corrected the unit test assertion for `sanitize_original_filename('vendor\r\n"report".pdf')` / `build_content_disposition(...)` from `'inline; filename="vendor _report_.pdf"'` to `'inline; filename="vendor_report_.pdf"'`, matching `_CONTROL_CHARS_RE` + `_SAFE_FILENAME_CHARS_RE` behavior without weakening filename sanitization.
2. **PostgreSQL `FAILED` Scan Status Alignment (`backend/app/models/accounting.py`, `backend/alembic/versions/0003_document_failed_scan_status.py`, `backend/tests/test_migrations.py`)**
   - Updated `Document` model constraint `ck_documents_document_scan_status_valid` and added forward Alembic migration `0003_doc_failed_scan_status` (revising `0002_invites_and_rate_limits`) so `documents.scan_status` permits `'PENDING'`, `'CLEAN'`, `'INFECTED'`, `'FAILED'`, and `'SKIPPED_DEV'` (with downgrade restoring the prior constraint and PostgreSQL migration constraint tests added).
3. **Pre-Multipart ASGI Upload Size Enforcement (`backend/app/services/storage_service.py`, `backend/app/main.py`)**
   - Added pure ASGI `DocumentUploadSizeLimitMiddleware` (alongside pure ASGI `RequestIdMiddleware`) scoped strictly to `POST /api/v1/workspaces/{workspaceId}/documents`, enforcing `MAX_DOCUMENT_UPLOAD_REQUEST_BYTES = 16 MiB` (`15 MB` file limit + `1 MiB` explicit multipart overhead) **before** Starlette multipart parsing/spooling.
   - Rejects oversized `Content-Length` headers immediately without invoking inner handlers and counts streamed request chunks for unannounced/chunked bodies, returning a single standard `413 FILE_TOO_LARGE` error envelope while leaving auth, CSRF, CORS, and all other routes intact.
4. **Inline PDF Response Hardening & NUL-Byte Validation (`backend/app/api/v1/documents.py`, `backend/app/services/document_service.py`)**
   - Added `Content-Security-Policy: sandbox` on inline `application/pdf` streaming responses (`download=false`) while keeping `X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store`, `CLEAN`-only gating, and unchanged `download=true` attachment behavior. *(CSP sandboxing provides browser defense-in-depth only and does not replace antivirus scanning or PDF sanitization.)*
   - Updated `_clean_optional_text()` and `upload_workspace_document()` to reject embedded `\x00` NUL bytes in `supplierName` and `invoiceNumber` with `422 VALIDATION_ERROR` before touching storage or PostgreSQL.

---

## Prior Completed Work on `main` (`fa89175a`)

- **Task 002.4A (`c0c0b615` + `fa89175a`):** Suppliers Master API (`GET`/`POST`/`PATCH` `/suppliers`, normalized name/GSTIN/PAN whitespace-before-length validation, `FOR UPDATE` + `IntegrityError` handling, SQL invoice aggregates, RBAC, CSRF, audit events).
- **Task 002.4B (`e255af40`):** Pluggable `DocumentStorage` + `LocalFilesystemStorage` (UUID keys, canonical path & symlink containment, 15 MB streaming cap, magic-byte validation, draft invoice staging, `CLEAN`-only content streaming).
- **Task 002.3 (`125857a` / `a873fcb`):** Auth/session/CSRF/RBAC foundation verified green on GitHub Actions CI #13 and CI #14.
- **Task 001 – 002.2B:** React 19 + TypeScript + Tailwind CSS v4 frontend SPA and FastAPI modular monolith foundation.

---

## Implemented vs. Deferred & Production-Readiness Boundary

- **Implemented & Locally Verified:** Python bytecode compilation (`python3 -m compileall -q backend/app backend/alembic backend/tests` -> exit `0`) and React frontend (`npm run lint`, `npm test`, `npm run build`).
- **Pending Live PostgreSQL 16 / Pytest Verification (`NOT RUN` in Container):** AI Studio container lacks `pytest`, FastAPI runtime deps, and PostgreSQL 16 (`python3 -m pytest` unavailable); full backend suite and Alembic `0003` migration tests must run on Python 3.12+ + PostgreSQL 16+ or via GitHub Actions CI.
- **Not Production-Ready:** Local `./var/documents` filesystem storage and absence of an antivirus engine (uploads remain `PENDING` and blocked from streaming) are intended for development/single-node testing only. Production deployment still requires object storage (`S3`/`MinIO`), asynchronous malware scanning (`ClamAV`/worker), per-workspace quotas/rate limits, orphan-blob reconciliation, and proxy edge body caps.
- **Deferred Milestones (Task 002.5+):** Invoices CRUD + GST/line-item reconciliation + duplicate warnings, Human Review endpoints (`/verify`, `/flag`, `/reopen`), Reporting CSV export, Frontend `WorkspaceContext` API wiring, and OCR/AI extraction workers.
