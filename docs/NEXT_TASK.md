# NEXT_TASK — Exact Next Recommended Development Task

## Immediate Blocker Before Task 002.5: CI #20 Step 9 Recovery

Remote `main` (`e022634a7e2265231f12e5a101ca631fd0374deb`) already includes the Task 002.4D `HTTP_413_REQUEST_ENTITY_TOO_LARGE` fixes, `task-002-4c.patch` removal, and `docs/DATABASE_SCHEMA.md` update, **but GitHub Actions CI #20 (`45008480467`) still fails at Backend Step 9 (`pytest -v -ra`)** while raw CI logs return `HTTP 403` without authentication.

Before starting Task 002.5 implementation:
1. Inspect the authenticated **GitHub Actions CI #20 (`45008480467`) Step 9 log** (or run the full backend suite locally on **Python 3.12 + PostgreSQL 16** against `e022634a`) to obtain the exact failing test name(s) and traceback(s).
2. Fix the root cause of the remaining Step 9 failure(s) on a feature branch off `e022634a7e2265231f12e5a101ca631fd0374deb` and remove the committed root `NORUS-TASK-002-4D.patch` artifact, then verify a 100% green CI run:

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
