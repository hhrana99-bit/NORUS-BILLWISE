# STATUS — Project Progress

**Current Milestone:** Task 002.4D — Backend CI Failure Investigation & Stabilization  
**Status:** Task 002.4D Changes Implemented Locally (on top of verified remote GitHub `main` commit `1adcbdcd558bac2821ade1db1b3ee4b5b4db7d6f`, whose CI #18 run `44877773232` passed Frontend CI and failed Backend Step 9 with `5 failed, 92 passed, 1 warning`; `pytest` and PostgreSQL 16 verification pending external Python 3.12 + PostgreSQL 16 / GitHub Actions CI run)

---

## Completed Work in Task 002.4D — Backend CI Stabilization & Hygiene

1. **Starlette HTTP 413 Constant Compatibility Fix (`backend/app/main.py`, `backend/app/services/storage_service.py`)**
   - Replaced all 6 occurrences of `status.HTTP_413_CONTENT_TOO_LARGE` (unsupported in the pinned `fastapi==0.115.6` / Starlette `<0.42` dependency set) with `status.HTTP_413_REQUEST_ENTITY_TOO_LARGE`, resolving the confirmed `AttributeError` in the four document upload/limit tests while preserving HTTP `413` status codes and `FILE_TOO_LARGE` error envelopes.
2. **Repository Hygiene & Schema Documentation Alignment**
   - Removed the committed `/task-002-4c.patch` diff artifact after confirming no scripts, tests, or workflows reference it.
   - Updated `docs/DATABASE_SCHEMA.md` (`documents.scan_status`) to include `'FAILED'` (`PENDING`, `CLEAN`, `INFECTED`, `FAILED`, `SKIPPED_DEV`).
   - Updated `docs/STATUS.md`, `docs/NEXT_TASK.md`, and `docs/TESTING.md` to reflect actual remote `main` commit `1adcbdcd558bac2821ade1db1b3ee4b5b4db7d6f` and CI #18 status.
3. **Unidentified Fifth CI #18 Failure**
   - CI #18 summary reported 5 failures, with 4 attributed to `HTTP_413_CONTENT_TOO_LARGE`. Because authenticated GitHub Actions step logs (`HTTP 403`) and local `pytest`/PostgreSQL 16 execution are unavailable in this container, the 5th failure remains unidentified and was not speculatively patched.

---

## Prior Completed Work on `main` (`1adcbdcd`)

- **Task 002.4C (`1adcbdcd`):** Migration `0003_doc_failed_scan_status` (`FAILED` scan status), pure ASGI `RequestIdMiddleware` & `DocumentUploadSizeLimitMiddleware` (`16 MiB` pre-multipart limit), inline PDF `Content-Security-Policy: sandbox`, pre-storage `\x00` NUL-byte validation on `supplierName`/`invoiceNumber`, and fixed `test_documents.py` filename assertion. *(Frontend CI passed; Backend Step 9 failed CI #18.)*
- **Task 002.4B (`e255af40`):** Pluggable `DocumentStorage` + `LocalFilesystemStorage` (UUID keys, canonical path & symlink containment, 15 MB streaming cap, magic-byte validation, draft invoice staging, `CLEAN`-only content streaming).
- **Task 002.4A (`c0c0b615` + `fa89175a`):** Suppliers Master API (`GET`/`POST`/`PATCH` `/suppliers`, normalized name/GSTIN/PAN whitespace-before-length validation, `FOR UPDATE` + `IntegrityError` handling, SQL invoice aggregates, RBAC, CSRF, audit events).
- **Task 002.3 (`125857a` / `a873fcb`):** Auth/session/CSRF/RBAC foundation verified green on GitHub Actions CI #13 and CI #14.
- **Task 001 – 002.2B:** React 19 + TypeScript + Tailwind CSS v4 frontend SPA and FastAPI modular monolith foundation.

---

## Implemented vs. Deferred & Production-Readiness Boundary

- **Implemented & Locally Verified:** Python bytecode compilation (`python3 -m compileall -q backend/app backend/alembic backend/tests` -> exit `0`) and React frontend (`npm run lint`, `npm test`, `npm run build`).
- **Pending Live PostgreSQL 16 / Pytest Verification (`BLOCKED` in Container):** AI Studio container lacks `pytest`, FastAPI runtime deps, and PostgreSQL 16; full backend suite execution (and diagnosis of the 5th CI #18 failure if still present) must run on Python 3.12 + PostgreSQL 16 or via GitHub Actions CI.
- **Not Production-Ready:** Local `./var/documents` filesystem storage and absence of an antivirus engine (uploads remain `PENDING` and blocked from streaming) are intended for development/single-node testing only. Production deployment still requires object storage (`S3`/`MinIO`), asynchronous malware scanning (`ClamAV`/worker), per-workspace quotas/rate limits, orphan-blob reconciliation, and proxy edge body caps.
- **Deferred Milestones (Task 002.5+):** Invoices CRUD + GST/line-item reconciliation + duplicate warnings, Human Review endpoints (`/verify`, `/flag`, `/reopen`), Reporting CSV export, Frontend `WorkspaceContext` API wiring, and OCR/AI extraction workers.
