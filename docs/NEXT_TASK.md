# NEXT_TASK — Exact Next Recommended Development Task

## Immediate Verification Prerequisite (Run Outside Container Runtime)

Before starting Task 002.4B implementation, merge/apply the Task 002.4A Suppliers Master PR on top of `main` (`a873fcb`) and run the full `pytest` suite on **Python 3.12+ + PostgreSQL 16+** (locally or via GitHub Actions CI) to verify `test_suppliers.py` alongside the existing backend suite:

```bash
cd backend
pip install -r requirements.txt
export TEST_DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/norus_billwise_test"
export NORUS_ALLOW_DESTRUCTIVE_MIGRATION_TEST=1
export NORUS_REQUIRE_POSTGRES_TESTS=1
alembic upgrade head
pytest -v -ra
```

---

## Next Development Milestone: NORUS BILLWISE TASK 002.4B — Secure `DocumentStorage` & Document Upload/Streaming API

### Objective
Implement workspace-scoped document upload, pluggable `DocumentStorage` persistence, content validation, malware-scan gating, and safe binary streaming for Review Centre side-by-side previewing—reusing existing Task 002.3 auth/CSRF/RBAC guards and the existing `documents` and `invoices` tables from migration `0001_initial_foundation`.

### Deliverables

1. **Dependencies (`backend/requirements.txt`, `backend/pyproject.toml`)**
   - Add pinned `python-multipart` for FastAPI `UploadFile` / `Form(...)` multipart parsing while keeping existing `httpx==0.27.2` and `pydantic-settings==2.7.0` pins intact.
2. **Document Schemas (`backend/app/schemas/documents.py`)**
   - Add `DocumentDto` and `DocumentUploadResponse` (`document`, nullable `invoiceId`) using `ApiModel` (`camelCase`, `extra="forbid"`).
3. **Pluggable `DocumentStorage` & `LocalFilesystemStorage` (`backend/app/services/storage_service.py`)**
   - Define a `DocumentStorage` Protocol/ABC (`save_stream`, `open_stream`, `delete`) to support future S3/MinIO adapters without changing domain logic.
   - Implement `LocalFilesystemStorage` rooted at `settings.document_storage_root`:
     - Generate deterministic server-only UUID storage keys (`orgs/{org_id}/workspaces/{ws_id}/{document_id}`).
     - Canonicalize paths via `Path.resolve()` and enforce strict containment inside `root.resolve()` to prevent directory traversal (`../`, symlink escapes).
     - Stream uploads in bounded chunks (`64 KB`), enforce the `15 MB` (`15_728_640` bytes) cap before buffering excess bytes (`413 FILE_TOO_LARGE`), inspect binary magic bytes (`%PDF-`, PNG, JPEG, WEBP) + extension/MIME consistency (`415 UNSUPPORTED_MEDIA_TYPE`), and compute `sha256_checksum` during streaming.
     - Integrate synchronous/pluggable malware-scan hook (`scan_status`: `CLEAN`, `INFECTED`, `PENDING`, `SKIPPED_DEV` per configuration) so infected uploads are quarantined/rejected and blocked from streaming.
4. **Document Domain Service & Router (`backend/app/services/document_service.py`, `backend/app/api/v1/documents.py`, `backend/app/api/v1/__init__.py`)**
   - Implement `POST /api/v1/workspaces/{workspaceId}/documents` (`WORKSPACE_ADMIN`, `REVIEWER`, `UPLOADER` + CSRF): persist file -> insert `documents` row -> optionally create staged `PENDING_REVIEW` draft `invoices` row (`createDraftInvoice=true` default, using workspace buyer snapshot defaults) -> emit `document.uploaded` audit event; clean up written storage file safely if the database transaction rolls back.
   - Implement `GET /api/v1/workspaces/{workspaceId}/documents/{documentId}/content` (`WORKSPACE_ADMIN`, `REVIEWER`, `UPLOADER`, `VIEWER`): enforce strict `workspace_id` isolation (`404` across workspaces), block `INFECTED` documents (`403`/`422`), set `X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store`, and `Content-Disposition: inline|attachment` (with sanitized filename) toggled by `download=true|false`.
5. **PostgreSQL 16 Tests (`backend/tests/test_documents.py`)**
   - Test valid PDF/PNG/JPG/WEBP uploads, optional draft invoice creation, magic-byte spoofing rejection (`415`), >15 MB bounded streaming rejection (`413`), path-traversal/filename sanitization, DB-failure storage rollback cleanup, `INFECTED` scan gating, `download=true|false` headers (`nosniff`, `no-store`), RBAC (`VIEWER` denied upload, `UPLOADER`/`REVIEWER`/`ADMIN` allowed), CSRF enforcement, and cross-workspace `404` isolation.

### Subsequent Tasks (Following Task 002.4B)
- **Task 002.5:** Invoices CRUD, Flexible Indian GST & Advisory Line-Item Reconciliation Engine, and Advisory Duplicate Detection.
- **Task 002.6:** Human Review Workflow (`/verify`, `/flag`, `/flags/{flagId}/resolve`, `/reopen`, `WORKSPACE_ADMIN` draft soft-delete, immutable `review_actions` & `audit_events`).
- **Task 002.7:** Reporting Aggregations, Formula-Safe CSV Export & Frontend `WorkspaceContext` API Integration (`credentials: 'include'` + `X-CSRF-Token`).
