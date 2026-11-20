# STATUS — Project Progress

**Current Milestone:** Task 002.4B — Document Storage & Upload/Streaming API  
**Status:** Task 002.4B Code & Tests Implemented Locally (on top of GitHub `main` commit `c0c0b6157d384dc63ed8e51d3fbb6f3ef14eddc8`, whose CI #15 run `44790860644` passed frontend checks and failed backend pytest Step 9; `pytest`, Alembic, and PostgreSQL 16 execution pending external Python 3.12+ / GitHub Actions CI run)

---

## Completed Work in Task 002.4B — Document Storage & Upload/Streaming API

1. **Dependencies & Config Validation (`backend/requirements.txt`, `backend/pyproject.toml`, `backend/app/core/config.py`)**
   - Pinned `python-multipart==0.0.20` for FastAPI `UploadFile` / `Form(...)` multipart parsing while keeping existing pins (`httpx==0.27.2`, `pydantic-settings==2.7.0`, etc.) untouched.
   - Validated non-blank `document_storage_root` in `Settings`.
2. **Pluggable `DocumentStorage` & `LocalFilesystemStorage` (`backend/app/services/storage_service.py`)**
   - Defined `DocumentStorage` Protocol (`save_stream`, `open_stream`, `delete`) for future S3/MinIO adapters.
   - Implemented `LocalFilesystemStorage` rooted at `settings.document_storage_root` with server-only UUID storage keys (`orgs/{org_id}/workspaces/{ws_id}/{document_id}.{ext}`), `Path.resolve()` canonical root containment (blocking `..`, backslashes, drive prefixes, null bytes, and symlink escapes), bounded `<= 64 KB` (`65,536` byte) chunked upload/download streaming, incremental `SHA-256` computation, atomic temp-file staging with `.part`/error cleanup, strict `15 MB` (`15,728,640` bytes) cap (`413 FILE_TOO_LARGE`), `0`-byte rejection (`422 EMPTY_FILE`), extension + declared MIME + binary magic-byte inspection (`%PDF-`, PNG, JPEG, WEBP -> `415 UNSUPPORTED_MEDIA_TYPE`), and strict ASCII single-component `sanitize_original_filename`.
3. **Document Domain Service, Schemas & Router (`backend/app/schemas/documents.py`, `backend/app/services/document_service.py`, `backend/app/api/v1/documents.py`, `backend/app/api/v1/__init__.py`)**
   - Implemented `POST /api/v1/workspaces/{workspaceId}/documents` (`WORKSPACE_ADMIN`, `REVIEWER`, `UPLOADER` + `require_csrf`): stores verified stream, creates `Document` (`scanStatus = "PENDING"`, never exposing `storageKey`), optionally creates a staged `PENDING_REVIEW` draft `Invoice` (`createDraftInvoice = true` default, populated with `WorkspaceSettings` buyer defaults and composite `(workspace_id, document_id)` FK), emits `document.uploaded` audit event, and rolls back DB + removes written storage file on DB failure.
   - Implemented `GET /api/v1/workspaces/{workspaceId}/documents/{documentId}/content` (`WORKSPACE_ADMIN`, `REVIEWER`, `UPLOADER`, `VIEWER`): enforces `workspace_id` isolation (`404` across workspaces), **blocks all non-`CLEAN` scan statuses** (`INFECTED` -> `403 DOCUMENT_INFECTED`; `PENDING`, `SKIPPED_DEV`, `FAILED` -> `409 DOCUMENT_SCAN_NOT_CLEAN`), and streams exact bytes with `X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store`, `Content-Disposition: inline|attachment`, `Content-Length`, and server-verified `Content-Type`.
   - **Malware Scanning & Storage Boundary:** No live antivirus daemon (e.g., ClamAV) is integrated in Task 002.4B. New uploads stay `PENDING` and remain blocked from `/content` in all environments until explicitly marked `CLEAN`. Local filesystem storage is intended for single-node dev/testing; production deployments require S3/MinIO + async malware scanning worker.
4. **Documents Unit & PostgreSQL 16 Tests (`backend/tests/test_documents.py`)**
   - Added offline unit tests (blank `document_storage_root`, filename/header sanitization, `storageKey` omission, extension/MIME/magic-byte spoofing, path-traversal/symlink escape rejection, bounded `<= 64 KB` chunk tracking, `15 MB` boundary & `15 MB + 1` cleanup, `PENDING`/`SKIPPED_DEV`/`FAILED`/`INFECTED`/`CLEAN` gating) plus PostgreSQL 16 integration tests (PDF/PNG/JPEG/WEBP uploads, draft invoice & audit event creation, spoofed/empty/>15 MB rejections with zero disk leftovers, DB-failure storage rollback cleanup, RBAC, CSRF, cross-workspace `404` isolation, and safe streaming headers).

---

## Prior Completed & Audited Work

- **Task 002.4A — Suppliers Master API (`c0c0b6157d384dc63ed8e51d3fbb6f3ef14eddc8` on `main`):** Suppliers schemas, service (`LIKE` escaping, SQL aggregates excluding soft-deleted invoices, `FOR UPDATE` + `IntegrityError` handling), router, and `test_suppliers.py`. **Note:** GitHub Actions CI #15 (`44790860644`) on `c0c0b615` passed Frontend CI and failed Step 9 (`pytest -v -ra`, exit code 1; raw job logs require GitHub auth). Live PostgreSQL 16 debugging/verification on CI #15 is still needed.
- **Task 002.3 CI Recovery & Auth/Tenancy (`125857a` / `a873fcb`):** Verified GitHub Actions **CI #13 (`44326415648`)** and **CI #14 (`44376162876`) PASS** across Frontend (`Node 22`) and Backend (`Python 3.12` + `PostgreSQL 16`, `62` `pytest` tests).
- **Task 001 – 002.2B:** React 19 + TypeScript + Tailwind CSS v4 frontend SPA and FastAPI modular monolith foundation.

---

## Implemented vs. Deferred Breakdown

- **Implemented & Locally Verified (`src/` + frontend tooling):** React 19 SPA with `npm run lint`, `npm test` (`11 passed`), and `npm run build` passing.
- **Implemented in `/backend` (Static Bytecode Compilation Verified Here; `pytest`/PostgreSQL 16 `NOT RUN` Locally):** Tasks 002.2, 002.3, Task 002.4A Suppliers Master API, and Task 002.4B Document Storage & Upload/Streaming API (`storage_service.py`, `document_service.py`, `schemas/documents.py`, `api/v1/documents.py`, `tests/test_documents.py`).
- **Container Environment Verification Boundary:** Local AI Studio container runs Python `3.11.2` without `pip`, `pytest`, `alembic`, FastAPI runtime deps, or PostgreSQL 16; live `pytest` execution of `test_suppliers.py` and `test_documents.py` requires running on Python 3.12+ + PostgreSQL 16+ or via GitHub Actions CI.
- **Not Yet Implemented (Task 002.5+):** Async antivirus scanner (ClamAV) & production S3/MinIO adapter, Invoices CRUD + GST/line-item reconciliation + duplicate warnings, Human Review endpoints (`/verify`, `/flag`, `/reopen`), Reporting CSV export, Frontend `WorkspaceContext` API wiring, and Task 003+ OCR/AI extraction.
