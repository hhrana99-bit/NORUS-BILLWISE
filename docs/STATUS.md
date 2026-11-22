# STATUS — Project Progress

**Current Milestone:** Task 002.4H — Consolidated CI Stabilization, Hygiene Cleanup & MVP Readiness  
**Status:** Verified Remote `main` (`b3e0460959e996260a51f3c0e35673ee943640a4`) **CI #22 GREEN** (`45010488214`); Root Patch Hygiene & Docs Cleanup Applied Locally

---

## Completed Work in Task 002.4G / 002.4H (`b3e04609` + Cleanup)

1. **Green CI Recovery (`b3e04609` — GitHub Actions CI #22, Run `45010488214`)**
   - Merged the Task 002.4G `backend/tests/test_documents.py` case-insensitive regex fix for `test_settings_rejects_blank_document_storage_root` into remote `main`.
   - Confirmed both CI #22 jobs passed (`success`): `Frontend Lint, Test & Build (Node 22)` and `Backend Compilation, Pytest & PostgreSQL 16 Migrations` (`compileall`, `pip install`, `NoDecode`/`Settings`, `alembic upgrade head`, and `pytest -v -ra`).
2. **Task 002.4H Repository & Documentation Cleanup**
   - Removed the obsolete committed root patch file `NORUS-TASK-002-4D.patch` (`83,931` bytes) after verifying zero references in code, tests, or CI workflows.
   - Synchronized `README.md`, `docs/STATUS.md`, `docs/NEXT_TASK.md`, `docs/TESTING.md`, and `docs/BACKEND_ARCHITECTURE.md` with verified baseline `b3e04609` and CI #22 green status.

---

## Prior Completed Work on `main` (`b3e04609` and earlier)

- **Task 002.4D (`a793a7f9` → `f7cd90c4`):** `status.HTTP_413_REQUEST_ENTITY_TOO_LARGE` Starlette compatibility fix in `backend/app/main.py` and `backend/app/services/storage_service.py`, plus `task-002-4c.patch` removal.
- **Task 002.4C (`1adcbdcd`):** Migration `0003_doc_failed_scan_status` (`FAILED` scan status), pure ASGI `RequestIdMiddleware` & `DocumentUploadSizeLimitMiddleware` (`16 MiB` pre-multipart limit), inline PDF `Content-Security-Policy: sandbox`, and pre-storage `\x00` NUL-byte validation on `supplierName`/`invoiceNumber`.
- **Task 002.4B (`e255af40`):** Pluggable `DocumentStorage` + `LocalFilesystemStorage` (UUID keys, canonical path & symlink containment, `15 MB` streaming cap, magic-byte validation, optional draft invoice staging, `CLEAN`-only content streaming).
- **Task 002.4A (`c0c0b615` + `fa89175a`):** Suppliers Master API (`GET`/`POST`/`PATCH` `/suppliers`, GSTIN/PAN whitespace trimming before max-length validation, `FOR UPDATE` + `IntegrityError` handling, SQL invoice aggregates, RBAC, CSRF, audit events).
- **Task 002.3 (`125857a` / `a873fcb`):** Auth/session/CSRF/RBAC foundation with Argon2id, `HttpOnly`/`SameSite=Lax` cookies, rotating refresh token families, PostgreSQL rate limiting, and anti-enumeration invitations.
- **Task 001 – 002.2B:** React 19 + TypeScript + Tailwind CSS v4 frontend SPA and FastAPI modular monolith foundation.

---

## Implemented vs. Deferred & MVP-Readiness Boundary

- **Locally Executed & Passing (Container):** Python bytecode compilation (`python3 -m compileall -q backend/app backend/alembic backend/tests`) and React frontend (`npm run lint`, `npm test`, `npm run build`).
- **Remotely Passing / Locally Blocked:** GitHub Actions **CI #22 (`45010488214`) PASSED** (`pytest -v -ra` + PostgreSQL 16 migrations). Live `pytest` and PostgreSQL 16 migration execution remain `BLOCKED` inside this container due to absent Python 3.12, backend dependencies, and PostgreSQL 16.
- **A. Required Before Controlled Accounting-Firm Pilot:**
  - **Task 002.5:** Invoices CRUD, flexible Indian GST & line-item `Decimal` reconciliation engine, and advisory duplicate detection.
  - **Task 002.6:** Human Review workflow endpoints (`/verify`, `/flag`, `/flags/{flagId}/resolve`, `/reopen`, `WORKSPACE_ADMIN` unverified soft-delete, immutable `review_actions` & `audit_events`).
  - **Task 002.7:** Backend Reports API (`/summary`, `/monthly-trend`, `/exceptions`, `/export.csv`) and Frontend `WorkspaceContext` API integration (`credentials: 'include'` + `X-CSRF-Token`, auth/workspace UI).
  - **Document Scan & Pilot Storage Readiness:** Wire real malware scanning (e.g., ClamAV async/inline worker) or a controlled non-production `CLEAN` transition gate so uploaded PDFs/images become streamable during pilot review, plus pilot HTTPS deployment config (`COOKIE_SECURE=true`, production `CORS_ORIGINS`, `TRUSTED_PROXIES`, persistent volume/object storage).
- **B. Required Before Production Deployment:**
  - Encrypted S3/MinIO `DocumentStorage` adapter + lifecycle orphan-blob cleanup, mandatory ClamAV malware scanning pipeline, upload/stream rate limits & workspace storage quotas, automated PostgreSQL backups + PITR restore drills, email verification & password-reset flows, data retention/deletion workflows, and structured monitoring/alerting.
- **C. Later Releases (Post-MVP):**
  - Automated OCR/AI field extraction + bounding-box evidence workers, bulk CSV/ERP export adapters (Tally/Zoho/SAP), and multi-office practice analytics.
