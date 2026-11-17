# NORUS BILLWISE Backend (`/backend`)

**Company:** NORUS AI  
**Product:** NORUS BILLWISE (*Beyond the World.*)  
**Current Milestone:** Task 002.2 — Backend Foundation, Database Engine & Initial Migrations

---

## 1. Architecture Summary

This directory contains the portable Python FastAPI + PostgreSQL + SQLAlchemy 2.0 + Alembic backend foundation designed in `docs/BACKEND_ARCHITECTURE.md`, `docs/DATABASE_SCHEMA.md`, and `docs/API_CONTRACT.md` (with Task 002.1A finalized decisions).

### Package Layout

```text
backend/
├── .env.example
├── .gitignore
├── README.md
├── pyproject.toml
├── requirements.txt
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 0001_initial_foundation.py
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app factory + CORS + lifespan
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       └── health.py        # GET /api/v1/health, GET /api/v1/ready
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py            # Pydantic BaseSettings & fail-fast security guards
│   │   └── logging.py           # Structured application logging setup
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py              # DeclarativeBase + deterministic naming convention
│   │   └── session.py           # PostgreSQL engine, sessionmaker, get_db dependency
│   ├── models/
│   │   ├── __init__.py          # Central export for Alembic metadata
│   │   ├── tenancy.py           # organizations, users, user_sessions, workspaces, workspace_settings, memberships
│   │   ├── accounting.py        # suppliers, documents, invoices, invoice_line_items, invoice_field_verifications
│   │   └── review.py            # invoice_review_flags, review_actions, audit_events
│   └── schemas/
│       ├── __init__.py
│       └── base.py              # Shared ApiModel (camelCase JSON wire format, extra="forbid")
└── tests/
    ├── conftest.py
    ├── test_config.py
    ├── test_schemas.py
    ├── test_health_and_app.py
    ├── test_models.py
    └── test_migrations.py
```

---

## 2. Finalized Architectural Contracts Enforced Here

1. **API JSON Naming (`app/schemas/base.py`):**
   - Python internals and PostgreSQL columns strictly use `snake_case`.
   - `ApiModel` serializes to `camelCase` (`alias_generator=to_camel`, `populate_by_name=True`, `extra="forbid"`).
2. **Mandatory Human Review & Soft-Delete Safeguards (`app/models/`, `0001_initial_foundation.py`):**
   - `workspace_settings` enforces `CHECK (require_human_review = true)`.
   - `invoices` enforces `CHECK ((status != 'VERIFIED') OR (verified_by_user_id IS NOT NULL AND verified_at IS NOT NULL))`.
   - `invoices` enforces `CHECK ((deleted_at IS NULL) OR (status IN ('PENDING_REVIEW', 'FLAGGED')))` so `VERIFIED` invoices can never be soft-deleted, while `invoice_review_flags` and `review_actions` retain `ON DELETE RESTRICT` integrity.
   - `invoices` supports advisory `line_item_reconciliation_status` (`NO_LINE_ITEMS`, `MATCHED`, `VARIANCE_WARNING`) without auto-rejecting invoices.
3. **Session Store Ready for Cookie Auth (`user_sessions`):**
   - Includes `token_family_id`, `refresh_token_hash`, `replaced_by_session_id`, `rotated_at`, `revoked_at`, and `revoke_reason` for Task 002.3 cookie auth + rotation + reuse detection.

---

## 3. Prerequisites & Local Setup

- **Python:** `3.12+` recommended (`requires-python = ">=3.12"` in `pyproject.toml`; codebase avoids post-3.10 syntax quirks where practical)
- **PostgreSQL:** `16+`

### Install Dependencies

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Configure Environment Variables

```bash
cp .env.example .env
# Edit DATABASE_URL and replace JWT_SECRET_KEY (>= 32 characters)
```

Key environment variables (`backend/.env.example`):

| Variable | Description |
| --- | --- |
| `APP_NAME` | Service display name (`NORUS BILLWISE API`) |
| `APP_ENV` | `development`, `test`, `staging`, or `production` |
| `API_V1_PREFIX` | Versioned API prefix (`/api/v1`) |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |
| `DATABASE_URL` | PostgreSQL URL (`postgresql+psycopg://...`) |
| `JWT_SECRET_KEY` | Signing secret (`>= 32` characters; placeholder blocked in staging/production) |
| `COOKIE_SECURE` | Cookie `Secure` flag (`true` required in staging/production) |
| `CORS_ORIGINS` | Comma-separated string or JSON array of explicit origins (wildcard `*` prohibited) |
| `DOCUMENT_STORAGE_ROOT` | Local filesystem root for document storage adapter (`./var/documents`) |

---

## 4. Database Migrations (Alembic + PostgreSQL)

Ensure PostgreSQL is running and the target database (e.g. `norus_billwise`) exists:

```bash
cd backend
alembic upgrade head
```

Verify downgrade and clean re-upgrade:

```bash
alembic downgrade base
alembic upgrade head
```

---

## 5. Running the Development Server

Start Uvicorn on a free local port (avoid port `3000`, which runs the Vite frontend):

```bash
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Probe health endpoints:

- `GET http://127.0.0.1:8000/api/v1/health` -> `{"status":"ok","service":"norus-billwise-api","environment":"development"}`
- `GET http://127.0.0.1:8000/api/v1/ready` -> `200` `{"status":"ready","database":"connected","detail":null}` (or `503` without exposing credentials if DB is unreachable)

---

## 6. Running Tests (`pytest`) & Destructive Migration Guard

Unit, config, schema, health/readiness, SQLAlchemy metadata, and pre-connection migration safety tests run without PostgreSQL (`test_alembic_upgrade_and_downgrade_on_postgresql` skips cleanly when `TEST_DATABASE_URL` is unset):

```bash
cd backend
pytest -v
```

### Dedicated Test Database & Opt-In Safety Controls

Because `test_alembic_upgrade_and_downgrade_on_postgresql` runs `alembic downgrade base` (which **drops all tables**), `tests/test_migrations.py` enforces a strict pre-connection safety guard before opening any connection or invoking Alembic:

1. **Scheme:** Only `postgresql://` or `postgresql+psycopg://` is allowed.
2. **Exact Database Name:** Must equal `norus_billwise_test` (development `norus_billwise`, default `postgres`, `staging`, `production`, and arbitrary names are rejected).
3. **Approved Hosts Only:** `localhost`, `127.0.0.1`, `::1`, and the CI service hostname `postgres`.
4. **Explicit Destructive Opt-In:** `NORUS_ALLOW_DESTRUCTIVE_MIGRATION_TEST=1` must be exported whenever `TEST_DATABASE_URL` is set.
5. **Required PostgreSQL Mode (`CI`):** Setting `NORUS_REQUIRE_POSTGRES_TESTS=1` causes missing `TEST_DATABASE_URL` or an unreachable PostgreSQL instance to **fail** rather than skip.

Run the full suite including live PostgreSQL migration `upgrade -> downgrade -> upgrade` locally against an isolated `norus_billwise_test` database:

```bash
export TEST_DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/norus_billwise_test"
export NORUS_ALLOW_DESTRUCTIVE_MIGRATION_TEST=1
export NORUS_REQUIRE_POSTGRES_TESTS=1
pytest -v -ra
```

It never substitutes SQLite for PostgreSQL migrations and never prints credentials in error messages.

---

## 7. Automated GitHub Actions CI (`.github/workflows/ci.yml`)

- `verify-frontend` preserves Node 22 linting, service tests, and Vite production build.
- `verify-backend` provisions **Python 3.12** + a **PostgreSQL 16** service container (`norus_billwise_test` with `pg_isready` health check), installs `backend/requirements.txt` (`pydantic-settings==2.7.0` for `NoDecode`), verifies Python compilation and `NoDecode` / `Settings` loading, runs `alembic upgrade head`, and executes `pytest -v -ra` with `NORUS_REQUIRE_POSTGRES_TESTS=1` and `NORUS_ALLOW_DESTRUCTIVE_MIGRATION_TEST=1`.

---

## 8. Implemented vs. Deferred Scope

- **Implemented in Task 002.2 + Task 002.3 Batch 1:** Config validation (`pydantic-settings==2.7.0` + `NoDecode` + comma/JSON/list `CORS_ORIGINS`), logging, `ApiModel` base DTOs, FastAPI app factory (`create_app`), `/api/v1/health` & `/api/v1/ready`, SQLAlchemy 2.0 declarative base + session management, all 15 ORM models, Alembic URL precedence + `0001_initial_foundation` migration, destructive migration safety guards & unit tests, and PostgreSQL 16 CI workflow.
- **Not Implemented Yet (Task 002.3 Batch 2+):** Cookie authentication endpoints/CSRF guard, Organizations/Workspaces/RBAC routes, Suppliers & Document upload/storage routes, Invoices/GST/reconciliation CRUD, Human Review workflow endpoints, Reports/CSV export, OCR/AI extraction, and Frontend-to-Backend API integration.
- **Container Environment Note:** Inside the AI Studio container runtime (`Python 3.10.12`, no `pip`/`uv`, no PostgreSQL server), Python bytecode compilation passes, while `pip install`, live `NoDecode` import, `pytest`, and PostgreSQL 16 migration execution remain pending remote GitHub Actions CI or a local Python 3.12+ + PostgreSQL 16+ environment.
