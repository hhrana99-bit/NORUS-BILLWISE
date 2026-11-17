# NEXT_TASK — Exact Next Recommended Development Task

## Immediate Verification Prerequisite (Run Outside Container Runtime)

Before starting Task 002.4 feature endpoints, push/sync Task 002.3 Batch 2 to GitHub `main` (or execute locally on **Python 3.12+ + PostgreSQL 16+**) to verify the Batch 2 `pytest` and CI suite:

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

## Next Development Milestone: NORUS BILLWISE TASK 002.4 — Suppliers Master & Secure Document Storage (`DocumentStorage`)

### Objective
Implement workspace-scoped Suppliers Master CRUD and secure invoice document upload/streaming on top of the verified Task 002.3 cookie authentication, CSRF protection, and RBAC membership guards.

### Deliverables

1. **Suppliers Master Service & API (`app/api/v1/suppliers.py`, `app/services/supplier_service.py`, `app/schemas/suppliers.py`)**
   - Implement `GET /api/v1/workspaces/{workspaceId}/suppliers` (search, `status` filter, pagination, SQL-aggregated `totalInvoices`, `totalValue`, `lastInvoiceDate` excluding soft-deleted invoices).
   - Implement `POST /api/v1/workspaces/{workspaceId}/suppliers` (`WORKSPACE_ADMIN`, `REVIEWER` + CSRF) with server-side `normalized_name` computation and GSTIN validation.
   - Implement `GET /api/v1/workspaces/{workspaceId}/suppliers/{supplierId}` and `PATCH /api/v1/workspaces/{workspaceId}/suppliers/{supplierId}` with strict `workspace_id` isolation (`404` across workspaces).
2. **Pluggable Document Storage & Upload/Streaming (`app/services/storage_service.py`, `app/api/v1/documents.py`)**
   - Implement `DocumentStorage` interface (`save`, `open_stream`, `delete`) with initial `LocalFilesystemStorage` rooted at `settings.document_storage_root`, path-traversal protection, and SHA-256 checksum computation.
   - Implement `POST /api/v1/workspaces/{workspaceId}/documents` (`WORKSPACE_ADMIN`, `REVIEWER`, `UPLOADER` + CSRF): 15 MB size limit (`413 FILE_TOO_LARGE`), magic-byte MIME verification (`415 UNSUPPORTED_MEDIA_TYPE` for non-PDF/PNG/JPG/WEBP), `AuditEvent` logging, and optional draft `PENDING_REVIEW` invoice creation.
   - Implement `GET /api/v1/workspaces/{workspaceId}/documents/{documentId}/content` streaming with `X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store`, and `Content-Disposition` toggling via `download=true|false`.
3. **Tests**
   - Add PostgreSQL 16 integration tests covering supplier aggregates (excluding soft-deleted invoices), role gates (`VIEWER`/`UPLOADER` vs `REVIEWER`/`WORKSPACE_ADMIN`), magic-byte spoof rejection, oversized file rejection, path-traversal safety, content streaming headers, and cross-workspace `404` isolation.

### Subsequent Tasks (Following Task 002.4)
- **Task 002.5:** Invoices CRUD, Flexible Indian GST & Advisory Line-Item Reconciliation Engine, and Advisory Duplicate Detection.
- **Task 002.6:** Human Review Workflow (`/verify`, `/flag`, `/flags/{flagId}/resolve`, `/reopen`, `WORKSPACE_ADMIN` draft soft-delete, immutable `review_actions` & `audit_events`).
- **Task 002.7:** Reporting Aggregations, Formula-Safe CSV Export & Frontend `WorkspaceContext` API Integration (`credentials: 'include'` + `X-CSRF-Token`).
