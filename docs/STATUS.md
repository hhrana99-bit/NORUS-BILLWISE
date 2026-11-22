# STATUS — Project Progress

**Current Milestone:** Task 002.4G — Fix Final Document Settings Test Failure  
**Status:** Task 002.4G Fix Implemented Locally (on top of verified remote GitHub `main` commit `f7cd90c49689fe6e93aab96bbffa269ecbe7a35f`, whose CI #21 run `45009400338` passed Frontend CI and failed Backend Step 9 with `1 failed, 96 passed, 1 warning`; live `pytest` and PostgreSQL 16 execution pending external Python 3.12 + PostgreSQL 16 / GitHub Actions CI run)

---

## Completed Work in Task 002.4G (`f7cd90c4` + Local Repair)

1. **Fixed `test_settings_rejects_blank_document_storage_root` (`backend/tests/test_documents.py`)**
   - Confirmed `backend/app/core/config.py` properly rejects blank `DOCUMENT_STORAGE_ROOT` with `ValueError("DOCUMENT_STORAGE_ROOT cannot be blank.")`.
   - Updated the `pytest.raises(ValidationError, match=...)` assertion in `test_documents.py` from lowercase `"document_storage_root"` to case-insensitive `r"(?i)DOCUMENT_STORAGE_ROOT cannot be blank\."` without weakening validation or altering application config behavior.
2. **Prior Task 002.4D/E Status on `main` (`a793a7f9` → `e022634a` → `f7cd90c4`)**
   - All 6 `HTTP_413_REQUEST_ENTITY_TOO_LARGE` compatibility fixes, `task-002-4c.patch` removal, and `docs/` updates are live on `main` (`f7cd90c4`); `NORUS-TASK-002-4D.patch` remains in repo root from `e022634a`.

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
