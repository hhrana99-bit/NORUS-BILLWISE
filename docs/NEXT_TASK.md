# NEXT_TASK — Exact Next Recommended Development Task

## Immediate Verification Prerequisite (Run Outside Container Runtime)

Before starting Task 002.5 implementation:
1. Synchronize Task 002.4C (`test_documents.py`, migration `0003_doc_failed_scan_status`, ASGI pre-multipart upload size limit, inline PDF `Content-Security-Policy: sandbox`, NUL-byte validation, and docs) onto a feature branch off `fa89175a09404f4a1cedfa9a2a296da2b25c1553`.
2. Run the full `pytest` suite and Alembic upgrade/downgrade cycle on **Python 3.12+ + PostgreSQL 16+** (locally or via GitHub Actions CI) and confirm green Step 9 CI:

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

## Next Development Milestone: NORUS BILLWISE TASK 002.5 — Invoices CRUD, Flexible Indian GST & Line-Item Reconciliation Engine, and Advisory Duplicate Detection

### Objective
Implement the core invoice lifecycle APIs on top of Task 002.4A (`suppliers`) and Task 002.4B/C (`documents`), delivering flexible GST & line-item reconciliation, advisory duplicate detection, strict RBAC/CSRF/tenant isolation, and mandatory human-review gating (never auto-verifying invoices).

### Deliverables

1. **Invoice Schemas & Decimal Calculators (`backend/app/schemas/invoices.py`, `backend/app/services/reconciliation_service.py`)**
   - Support list filtering/sorting/pagination (`GET /api/v1/workspaces/{workspaceId}/invoices`), manual/document-linked creation (`POST`, always initializing in `PENDING_REVIEW` and never `VERIFIED`), detail retrieval (`GET /{invoiceId}`), and partial updates (`PATCH /{invoiceId}`, locked against editing `VERIFIED` invoices unless reopened).
   - Compute `computedExpectedTotal`, `varianceAmount`, `reconciliationStatus`, `lineItemsTaxableSum`, `lineItemVarianceAmount`, `lineItemReconciliationStatus`, and advisory `lineItemWarning` strictly with fixed-point `Decimal` math without ever rejecting an invoice upload/save for arithmetic variance.
2. **Advisory Duplicate Warning Engine (`backend/app/services/invoice_service.py`)**
   - Detect workspace-scoped active (`deleted_at IS NULL`) invoices sharing supplier/normalized invoice number (respecting `WorkspaceSettings.enable_duplicate_warnings`) and populate advisory `duplicateWarning` for human review rather than silent rejection.
3. **Production Malware Scan & Object Storage Worker Hook (Preparation / Follow-on)**
   - Implement an S3/MinIO `DocumentStorage` adapter and an async malware scan worker (e.g., ClamAV) so validated `PENDING` uploads can progress safely to `CLEAN`, `INFECTED`, or `FAILED` before production deployment.
4. **PostgreSQL 16 Integration Tests (`backend/tests/test_invoices.py`)**
   - Cover GST intra/inter-state & `PRE_TAX`/`POST_TAX_COMMERCIAL` discount arithmetic, rounding tolerance, line-item variance advisories, duplicate warnings, `UPLOADER` edit restriction to `PENDING_REVIEW` only, `VERIFIED` lock (`409 VERIFIED_INVOICE_LOCKED`), soft-deleted invoice exclusion, CSRF, and cross-workspace `404` isolation.

### Subsequent Tasks (Following Task 002.5)
- **Task 002.6:** Human Review Workflow (`/verify`, `/flag`, `/flags/{flagId}/resolve`, `/reopen`, `WORKSPACE_ADMIN` draft soft-delete, immutable `review_actions` & `audit_events`).
- **Task 002.7:** Reporting Aggregations, Formula-Safe CSV Export & Frontend `WorkspaceContext` API Integration (`credentials: 'include'` + `X-CSRF-Token`).
