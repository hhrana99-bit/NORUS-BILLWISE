# STATUS — Project Progress

**Current Milestone:** Task 002.2 — Backend Foundation, Database Engine & Initial Migrations  
**Status:** Source & Tests Written / Environment Verification Partial (Static compile & frontend CI pass; Python runtime, `pytest`, and PostgreSQL `alembic` execution require Python 3.12+ + PostgreSQL outside this container)

---

## Completed Work in Task 002.2

1. **Portable `/backend` Service Skeleton**
   - Created `backend/pyproject.toml`, `backend/requirements.txt`, `backend/.env.example`, and `backend/.gitignore` using pinned dependencies (`fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`, `sqlalchemy`, `psycopg[binary]`, `alembic`, `python-dotenv`, `pytest`, `httpx`).
   - Created `app/core/config.py` (`Settings(BaseSettings)` enforcing PostgreSQL URLs, `>=32`-char `JWT_SECRET_KEY`, explicit `CORS_ORIGINS` without `*`, `COOKIE_SECURE=true` in staging/production, and credential redaction) and `app/core/logging.py`.
   - Created `app/schemas/base.py` (`ApiModel` with `to_camel`, `populate_by_name=True`, `from_attributes=True`, `extra="forbid"`, plus `HealthResponse`, `ReadyResponse`, `ErrorDetail`, `ErrorResponse`).
   - Created `app/main.py` (`create_app()` factory + lazy `app` export, CORS middleware, lifespan engine cleanup) and `app/api/v1/health.py` (`GET /api/v1/health` and `GET /api/v1/ready` returning `camelCase` JSON with 503 credential-safe DB failure responses).
2. **SQLAlchemy 2.0 Engine, Models & Alembic Migration**
   - Created `app/db/base.py` (deterministic PostgreSQL naming convention) and `app/db/session.py` (`create_db_engine`, `create_session_factory`, `get_db`).
   - Implemented all 15 ORM models matching `docs/DATABASE_SCHEMA.md` across `app/models/tenancy.py`, `app/models/accounting.py`, `app/models/review.py`, and `app/models/__init__.py` (`organizations`, `users`, `user_sessions`, `workspaces`, `workspace_settings`, `organization_memberships`, `workspace_memberships`, `suppliers`, `documents`, `invoices`, `invoice_line_items`, `invoice_field_verifications`, `invoice_review_flags`, `review_actions`, `audit_events`).
   - Configured Alembic (`backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`) and authored `0001_initial_foundation` (`upgrade()` + full reverse `downgrade()`).
3. **Backend Test Suite (`backend/tests/`) & Documentation (`backend/README.md`)**
   - Authored isolated `pytest` tests in `test_config.py`, `test_schemas.py`, `test_health_and_app.py`, `test_models.py`, and `test_migrations.py` (real PostgreSQL migration upgrade/downgrade test that skips cleanly when `TEST_DATABASE_URL` / PostgreSQL is unavailable).
4. **Frontend Preservation**
   - Kept the verified React 19 + TypeScript + Vite frontend (`src/`, `tests/`, `package.json`, `vite.config.ts`) completely intact and passing `npm run lint`, `npm test`, and `npm run build`.

---

## Completed Prior Milestones

- **Task 002.1 & Task 002.1A:** Architecture & schema specification (`docs/BACKEND_ARCHITECTURE.md`, `docs/DATABASE_SCHEMA.md`, `docs/API_CONTRACT.md`) finalizing `camelCase` API JSON, `HttpOnly`/`Secure`/`SameSite=Lax` cookie + CSRF auth, advisory line-item reconciliation warnings, and `WORKSPACE_ADMIN`-only soft deletion of unverified invoices.
- **Task 001 – 001.3:** React 19 + TypeScript + Tailwind CSS v4 frontend prototype, Playwright real-Chromium QA (`375px`, `768px`, `1280px` × 6 routes), 11 service unit tests, and `.github/workflows/ci.yml`.

---

## Implemented vs. Deferred Breakdown

- **Implemented & Verified in Frontend (`src/`):** React SPA with fictional Indian GST sample data, `localStorage` (`v2`) persistence, CSV formula-safe export, and browser-local file staging.
- **Implemented in `/backend` (Statically Verified Only):** FastAPI service skeleton, `Settings`, `ApiModel`, `/api/v1/health` & `/api/v1/ready`, SQLAlchemy 2.0 metadata (15 models), Alembic `0001_initial_foundation` migration, and `pytest` suite.
- **Not Yet Executed in This Container Runtime (Run Locally / in CI with Python 3.12+ & PostgreSQL 16+):** `pip install -r requirements.txt`, `pytest`, live `uvicorn` boot, and `alembic upgrade head` / `downgrade base` (container has Python `3.10.12`, no `pip`/`uv`, no PostgreSQL server, and port `8000` occupied).
- **Not Yet Implemented (Task 002.3+):** Cookie auth routes, CSRF guard, RBAC guards, supplier/document/invoice/review endpoints, reporting CSV API, frontend-to-backend integration, and Task 003+ OCR/AI extraction.
