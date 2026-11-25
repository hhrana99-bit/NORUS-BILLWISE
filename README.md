# NORUS BILLWISE

**Company:** NORUS AI  
**Product:** NORUS BILLWISE  
**Tagline:** *Beyond the World.*  
**Stage:** Task 002.7 — Reports API, Formula-Safe CSV Export & Frontend Workspace API Integration (`7d4783dc` baseline; Task 002.8 Next)

NORUS BILLWISE is an Invoice Intelligence and Verification Workspace built for Chartered Accountants, accounting firms, bookkeeping professionals, and business finance teams (initial target market: India; designed for global expansion).

---

## Current Implemented Scope

- **Frontend SPA (`src/`):** React 19 + TypeScript + Vite SPA wired directly to the FastAPI `/api/v1` backend via a centralized cookie + CSRF client (`src/services/apiClient.ts`, `src/services/apiMappers.ts`), `AuthScreen` (sign in / register), `WorkspaceContext` (multi-workspace switching, monotonic race guards, RBAC-aware actions), Dashboard, Invoices register, split-screen Review Centre (manual GST verification, mismatch safety gate, advisory duplicate checks, per-field review flags, immutable review history), Suppliers directory, Reports (KPIs, trend analytics, exceptions queue, server CSV export), and Settings (backend workspace settings + browser-only UI density preferences).
- **Backend Foundation (`backend/`):** Portable Python FastAPI + PostgreSQL 16+ service implementing:
  - SQLAlchemy 2.0 ORM models and Alembic migrations (`0001_initial_foundation`, `0002_invites_and_rate_limits`, and `0003_doc_failed_scan_status`)
  - Argon2id password hashing, `HttpOnly`/`SameSite=Lax` JWT access + rotating SHA-256 refresh cookies, `Origin`/`Referer` + double-submit CSRF checks, and PostgreSQL multi-worker auth rate limiting with `TRUSTED_PROXIES` IP/CIDR validation
  - Organization/workspace provisioning, anti-enumeration organization invitations, organization & workspace memberships with role-based access control (`WORKSPACE_ADMIN`, `REVIEWER`, `UPLOADER`, `VIEWER`), audit events, and mandatory `requireHumanReview = true` enforcement
  - **Suppliers Master API:** Workspace-scoped vendor CRUD (`GET`/`POST`/`PATCH`), GSTIN/PAN whitespace-before-length normalization, conflict handling, and SQL invoice aggregates
  - **Document Upload & Streaming (`LocalFilesystemStorage`):** Pure ASGI `16 MiB` pre-multipart upload cap, `15 MB` bounded chunk streaming, magic-byte signature validation, NUL-byte field validation, canonical path/symlink containment, `CLEAN`-only delivery (`FAILED`/`PENDING`/`SKIPPED_DEV` blocked with `409`, `INFECTED` with `403`), and inline PDF `Content-Security-Policy: sandbox`
  - **Invoices & GST Reconciliation API (`GET`/`POST`/`GET {id}`/`PATCH`/`DELETE`):** Fixed-point `Decimal` Indian GST & line-item reconciliation (non-blocking variances, structured discrepancies), canonical invoice number normalization, advisory duplicate detection (`NORMALIZED_INVOICE_NUMBER` + `SIMILAR_TOTAL_WITHIN_45_DAYS`), relationship/scan-status gating (`INFECTED`/`FAILED` rejected `409`), `VERIFIED` edit/delete locking, `WORKSPACE_ADMIN` soft-delete preserving audit/review trails, and search/filter/sort pagination
  - **Human Review Workflow & Immutable Audit Ledger (`/verify`, `/flag`, `/flags/{flagId}/resolve`, `/reopen`, `/review-history`, `/audit-events`):** Mandatory human verification (`WORKSPACE_ADMIN`, `REVIEWER` only), required field and header/line-item variance confirmation (`409 VARIANCE_ACKNOWLEDGMENT_REQUIRED`), exception flag lifecycle preserving resolved history, verified invoice reopen workflow, `SELECT ... FOR UPDATE` concurrency safety, and chronological/paginated immutable `review_actions` + sanitized `audit_events` history
  - **Reports & Formula-Safe CSV Export (`/reports/summary`, `/reports/monthly-trend`, `/reports/exceptions`, `/reports/export.csv`):** Single-query SQL `Decimal` KPI & GST aggregations, mixed-currency `409` protection, `DATE_TRUNC('month', ...)` zero-filled trends, batched exception feed, and RFC-4180 streaming CSV export with whitespace-aware formula-injection neutralization, `10,000`-row guard, RBAC enforcement (`UPLOADER` forbidden), and `report.csv_exported` audit logging
- **Not Implemented Yet (Task 002.8+):** Live malware scanning pipeline (`ClamAV` transitioning `PENDING -> CLEAN | INFECTED | FAILED`), production object storage (`S3`/`MinIO`), production deployment/backup hardening, OCR, and AI field extraction.

---

## Tech Stack

- **Frontend:** React 19, TypeScript (strict mode), Vite 8, Tailwind CSS v4 (`@tailwindcss/vite`), Lucide React, `npm`
- **Backend:** Python 3.12+, FastAPI, Pydantic v2 (`pydantic-settings`), SQLAlchemy 2.0, Alembic, PostgreSQL 16+ (`psycopg`), `argon2-cffi`, `PyJWT`, `pytest`

---

## Local Setup & Development

### Frontend

```bash
cp .env.example .env.local   # Optional: defaults to /api proxy targeting http://127.0.0.1:8000
npm ci
npm run dev
```

The frontend dev server runs on `http://localhost:3000` and proxies `/api` requests to `VITE_API_PROXY_TARGET` (default `http://127.0.0.1:8000`) so same-origin `HttpOnly` auth and CSRF cookies work locally alongside the FastAPI backend.

### Backend

> Requires Python 3.12+ and PostgreSQL 16+. See [`backend/README.md`](backend/README.md) for full configuration details.

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env
# Edit backend/.env with your local PostgreSQL DATABASE_URL and a >=32-character JWT_SECRET_KEY

alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

---

## Testing & Verification Commands

### Frontend

```bash
npm run lint
npm test      # 17 unit tests across tests/apiClient.test.ts and tests/services.test.ts
npm run build
```

### Backend

Run offline unit, config, schema, security, ORM model, and migration-guard tests:

```bash
cd backend
pytest -v
```

Run the complete suite including live PostgreSQL 16 migrations and auth/tenancy/RBAC integration tests against a dedicated `norus_billwise_test` database:

```bash
cd backend
export TEST_DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/norus_billwise_test"
export NORUS_ALLOW_DESTRUCTIVE_MIGRATION_TEST=1
export NORUS_REQUIRE_POSTGRES_TESTS=1
pytest -v -ra
```

CI (`.github/workflows/ci.yml`) runs both frontend (`npm ci`, `npm run lint`, `npm test`, `npm run build`) and backend (Python compilation, `alembic upgrade head`, `pytest -v -ra` against PostgreSQL 16) workflows on pushes and PRs to `main`.

---

## Important Current Limitations & Data Warning

- **Document scan pipeline still pending (Task 002.8):** Uploaded files persist to `LocalFilesystemStorage` with `scanStatus = "PENDING"`. Until automated malware scanning (`ClamAV`) is wired in Task 002.8, `/documents/{id}/content` strictly blocks non-`CLEAN` files (`409`) and the Review Centre shows a scan-status warning notice instead of rendering unscanned binaries.
- **No live OCR, AI extraction, or S3/MinIO yet:** Accounting fields are entered or updated manually against uploaded documents (`OCR`/`AI` workers are scheduled for Task 003+; production `S3`/`MinIO` object storage is scheduled for Task 002.8).
- **Not production-deployed:** Do not use this workspace for live customer accounting or production deployments yet.
- **Confidentiality warning:** **Never upload real confidential client or supplier invoices into local/staging environments before pilot hardening.** Use only fictional or sanitized test documents.
