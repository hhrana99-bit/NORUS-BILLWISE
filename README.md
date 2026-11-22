# NORUS BILLWISE

**Company:** NORUS AI  
**Product:** NORUS BILLWISE  
**Tagline:** *Beyond the World.*  
**Stage:** Task 002.4E — Backend Foundations Implemented Through Document Hardening (`e022634a`; CI #20 Backend Step 9 Recovery Next)

NORUS BILLWISE is an Invoice Intelligence and Verification Workspace built for Chartered Accountants, accounting firms, bookkeeping professionals, and business finance teams (initial target market: India; designed for global expansion).

---

## Current Implemented Scope

- **Frontend SPA (`src/`):** Standalone React prototype with Dashboard, Invoices register, split-screen Review Centre (manual GST verification, mismatch safety gate, advisory duplicate checks, per-field review flags), Suppliers directory, Reports (including formula-safe CSV export), and schema-versioned `localStorage` Settings.
- **Backend Foundation (`backend/`):** Portable Python FastAPI + PostgreSQL 16+ service implementing:
  - SQLAlchemy 2.0 ORM models and Alembic migrations (`0001_initial_foundation`, `0002_invites_and_rate_limits`, and `0003_doc_failed_scan_status`)
  - Argon2id password hashing, `HttpOnly`/`SameSite=Lax` JWT access + rotating SHA-256 refresh cookies, `Origin`/`Referer` + double-submit CSRF checks, and PostgreSQL multi-worker auth rate limiting with `TRUSTED_PROXIES` IP/CIDR validation
  - Organization/workspace provisioning, anti-enumeration organization invitations, organization & workspace memberships with role-based access control (`WORKSPACE_ADMIN`, `REVIEWER`, `UPLOADER`, `VIEWER`), audit events, and mandatory `requireHumanReview = true` enforcement
  - **Suppliers Master API:** Workspace-scoped vendor CRUD (`GET`/`POST`/`PATCH`), GSTIN/PAN whitespace-before-length normalization, conflict handling, and SQL invoice aggregates
  - **Document Upload & Streaming (`LocalFilesystemStorage`):** Pure ASGI `16 MiB` pre-multipart upload cap, `15 MB` bounded chunk streaming, magic-byte signature validation, NUL-byte field validation, canonical path/symlink containment, `CLEAN`-only delivery (`FAILED`/`PENDING`/`SKIPPED_DEV` blocked with `409`, `INFECTED` with `403`), and inline PDF `Content-Security-Policy: sandbox`
- **Not Implemented Yet (Task 002.5+):** Invoices CRUD & GST/line-item reconciliation endpoints, Human Review workflow endpoints (`/verify`, `/flag`, `/reopen`), backend Reporting/CSV export, live malware scanning & object storage (`S3`/`MinIO`), Frontend-to-Backend API wiring, OCR, and AI extraction.

---

## Tech Stack

- **Frontend:** React 19, TypeScript (strict mode), Vite 8, Tailwind CSS v4 (`@tailwindcss/vite`), Lucide React, `npm`
- **Backend:** Python 3.12+, FastAPI, Pydantic v2 (`pydantic-settings`), SQLAlchemy 2.0, Alembic, PostgreSQL 16+ (`psycopg`), `argon2-cffi`, `PyJWT`, `pytest`

---

## Local Setup & Development

### Frontend

```bash
npm ci
npm run dev
```

The frontend dev server runs on `http://localhost:3000`.

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
npm test
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

## Important Prototype Limitations & Data Warning

- **Frontend-only prototype state:** The React UI currently uses fictional Indian GST sample data (`src/data/mockData.ts`) and browser `localStorage` (`schemaVersion: 2`); it is **not** connected to the FastAPI backend yet.
- **No live OCR, AI extraction, or frontend-connected storage yet:** Files added in the **Upload Invoice** modal are previewed only in the browser via `URL.createObjectURL` because the React SPA is not yet wired to the FastAPI backend (`POST /documents`, `LocalFilesystemStorage` dev storage). Automated malware scanning, production object storage (`S3`/`MinIO`), and OCR/AI extraction are not yet built.
- **Not production-deployed:** Do not use this workspace for live customer accounting or production deployments yet.
- **Confidentiality warning:** **Never upload real confidential client or supplier invoices into the frontend-only prototype.** Use only fictional or sanitized test documents.
