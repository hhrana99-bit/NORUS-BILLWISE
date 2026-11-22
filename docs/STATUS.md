# STATUS — Project Progress

**Current Milestone:** Task 002.4E — Main Branch Verification, CI Recovery & MVP Completion Planning  
**Status:** Verified on remote `main` commit `e022634a7e2265231f12e5a101ca631fd0374deb` (parent `a793a7f9b21c651c353852afdb95c71fc5914541`). GitHub Actions **CI #20 (`45008480467`)** passed Frontend CI (`Node 22`) and Steps 1–8 of Backend CI (`compileall`, `pip install`, `Settings`, `alembic upgrade head` on PostgreSQL 16), and **failed Step 9 (`pytest -v -ra`)**. Full backend runtime verification remains `BLOCKED` in this container (Python 3.11 stdlib only, no PostgreSQL 16, and raw GitHub CI logs return `HTTP 403 Forbidden` without authentication).

---

## Verified State on `main` (`e022634a` / `a793a7f9`)

1. **Task 002.4D Changes Verified Live on `main` (`a793a7f9`)**
   - All 6 references to `status.HTTP_413_CONTENT_TOO_LARGE` in `backend/app/main.py` and `backend/app/services/storage_service.py` were replaced with `status.HTTP_413_REQUEST_ENTITY_TOO_LARGE` for `fastapi==0.115.6` / Starlette `<0.42` compatibility.
   - `task-002-4c.patch` was removed and `docs/DATABASE_SCHEMA.md` (`documents.scan_status`) was updated to document `'FAILED'`.
2. **Remaining Hygiene & CI Investigation Items (`e022634a`)**
   - Commit `e022634a` added `NORUS-TASK-002-4D.patch` (`83,931` bytes) into the repository root; it should be removed once CI Step 9 is diagnosed.
   - Both CI #19 (`44904905295` on `a793a7f9`) and CI #20 (`45008480467` on `e022634a`) still failed Backend Step 9 (`pytest -v -ra`), indicating at least one non-HTTP-413 failure (matching the unidentified 5th failure from CI #18) remains unaddressed. Exact tracebacks require authenticated GitHub CI logs or a Python 3.12 + PostgreSQL 16 test run.

---

## Prior Completed Work on `main` (`1adcbdcd` and earlier)

- **Task 002.4C (`1adcbdcd`):** Migration `0003_doc_failed_scan_status` (`FAILED` scan status), pure ASGI `RequestIdMiddleware` & `DocumentUploadSizeLimitMiddleware` (`16 MiB` pre-multipart limit), inline PDF `Content-Security-Policy: sandbox`, pre-storage `\x00` NUL-byte validation on `supplierName`/`invoiceNumber`, and fixed `test_documents.py` filename assertion.
- **Task 002.4B (`e255af40`):** Pluggable `DocumentStorage` + `LocalFilesystemStorage` (UUID keys, canonical path & symlink containment, 15 MB streaming cap, magic-byte validation, draft invoice staging, `CLEAN`-only content streaming).
- **Task 002.4A (`c0c0b615` + `fa89175a`):** Suppliers Master API (`GET`/`POST`/`PATCH` `/suppliers`, normalized name/GSTIN/PAN whitespace-before-length validation, `FOR UPDATE` + `IntegrityError` handling, SQL invoice aggregates, RBAC, CSRF, audit events).
- **Task 002.3 (`125857a` / `a873fcb`):** Auth/session/CSRF/RBAC foundation verified green on GitHub Actions CI #13 and CI #14.
- **Task 001 – 002.2B:** React 19 + TypeScript + Tailwind CSS v4 frontend SPA and FastAPI modular monolith foundation.

---

## Implemented vs. Deferred & MVP-Readiness Boundary

- **Locally Executed & Passing:** Python bytecode compilation (`python3 -m compileall -q backend/app backend/alembic backend/tests`) and React frontend (`npm run lint`, `npm test`, `npm run build`).
- **Blocked Locally / Failing Remotely:** `pytest -v -ra` and PostgreSQL 16 migration cycle (`BLOCKED` in container; **FAIL** at Step 9 of CI #20 `45008480467`).
- **Controlled Customer Pilot Blockers (Before Small Accounting Firm Testing):**
  - Resolve CI #20 Step 9 failure and achieve green `pytest` + PostgreSQL 16 CI.
  - Implement Invoices CRUD + GST/line-item reconciliation + duplicate warnings (Task 002.5), Human Review workflow (`/verify`, `/flag`, `/reopen`, Task 002.6), Reports API, and Frontend-to-Backend API wiring (Task 002.7).
  - Resolve document scan/preview usability for uploads (actual malware scanner or controlled non-production `CLEAN` workflow so uploaded PDFs/images can actually be viewed during review).
  - Production-grade auth/CORS/cookie config (`COOKIE_SECURE=true`, real domain `CORS_ORIGINS`, `TRUSTED_PROXIES`, persistent shared storage instead of ephemeral single-container filesystem).
- **Production Deployment Blockers:** Encrypted S3/MinIO object storage, automated ClamAV/malware scanning worker, automated PostgreSQL backups + PITR restore drills, data retention/deletion policy & privacy controls, monitoring/structured alerting/error tracking, and upload quotas/rate limits.
- **Post-MVP Enhancements:** Automated OCR/AI field extraction + bounding-box evidence workers, bulk CSV/ERP export adapters, and advanced multi-office practice analytics.
