# STATUS — Project Progress

**Current Milestone:** Task 002.3 Batch 1 — Dependency Compatibility, Migration Safety Hardening, Constraint Naming & PostgreSQL 16 Backend CI  
**Status:** Batch 1 Check-Constraint Naming Fix Prepared Locally (following GitHub Actions CI run `44096786203` on `783cb7c3a4b6be29536d8b8ec1f5102765a92369`; PostgreSQL 16 `pytest -v -ra` re-run pending push)

---

## Completed Work in Task 002.3 Batch 1

1. **Dependency Compatibility (`backend/requirements.txt`, `backend/pyproject.toml`, `backend/tests/test_config.py`)**
   - Updated `pydantic-settings` from `2.6.1` to `2.7.0` in both manifests so `from pydantic_settings import NoDecode` in `app/core/config.py` resolves cleanly alongside `pydantic==2.10.3`.
   - Pinned `httpx==0.27.2` in both manifests to match `fastapi==0.115.6` (`starlette<0.42.0`), fixing the `TestClient(app=...)` `TypeError` introduced by `httpx==0.28.1` during CI `pytest` execution.
   - Retained/expanded `test_config.py` regression coverage for comma-separated strings, JSON arrays, direct Python lists, wildcard rejection, and `NoDecode` import verification.
2. **PostgreSQL Check-Constraint Naming Fix & Regression Tests (`backend/alembic/versions/0001_initial_foundation.py`, `backend/tests/test_models.py`, `backend/tests/test_migrations.py`)**
   - Wrapped all 24 `sa.CheckConstraint(..., name=...)` declarations across all 11 tables in `0001_initial_foundation.py` with `op.f("ck_...")` so Alembic stops double-applying `Base.metadata`'s `"ck": "ck_%(table_name)s_%(constraint_name)s"` convention (`ck_invoices_ck_invoices_...`).
   - Added metadata and migration AST regression tests verifying canonical `ck_<table>_<name>` naming, PostgreSQL 63-byte identifier bounds, exact model-to-migration constraint alignment, and PostgreSQL 16 enforcement of `ck_invoices_invoice_verified_requires_human_actor`, `ck_invoices_invoice_soft_delete_unverified_only`, `ck_invoices_invoice_non_negative_amounts`, and `ck_invoices_invoice_discount_mode_valid`.
3. **Migration Test Database Safety Hardening (`backend/tests/test_migrations.py`)**
   - Added strict pre-connection guard (`validate_destructive_migration_target`) enforcing PostgreSQL schemes, exact DB name `norus_billwise_test`, approved local/CI hostnames (`localhost`, `127.0.0.1`, `::1`, `postgres`), explicit `NORUS_ALLOW_DESTRUCTIVE_MIGRATION_TEST=1` opt-in, clean skipping when `TEST_DATABASE_URL` is unset, explicit failure under `NORUS_REQUIRE_POSTGRES_TESTS=1`, and credential-free error messages.
   - Added zero-connection unit tests proving production/staging/development/default/`postgres` DB names, remote hosts, malformed URLs, and missing flags fail safely before calling `create_engine` or Alembic.
4. **PostgreSQL 16 GitHub Actions Backend CI (`.github/workflows/ci.yml`)**
   - Preserved `verify-frontend` (Node 22), removed obsolete `task-001-2-remediation` branch filter while keeping `main` push/PR triggers, and added `verify-backend` with Python 3.12, PostgreSQL 16 (`norus_billwise_test` + `pg_isready` health check), `alembic upgrade head`, and `pytest -v -ra` with `NORUS_REQUIRE_POSTGRES_TESTS=1` and `NORUS_ALLOW_DESTRUCTIVE_MIGRATION_TEST=1`.

---

## Completed Work in Task 002.2 & 002.2B

1. **Portable `/backend` Service Skeleton & ORM Models**
   - Implemented FastAPI `create_app()`, `Settings` (`NoDecode` comma/JSON CORS parsing), `ApiModel` (`camelCase` wire format), `/api/v1/health` & `/api/v1/ready`, SQLAlchemy 2.0 base/session management, all 15 ORM models matching `docs/DATABASE_SCHEMA.md`, Alembic URL precedence fix, and `0001_initial_foundation` migration.
2. **Frontend Preservation**
   - Kept the React 19 + TypeScript + Vite frontend (`src/`, `tests/`, `package.json`, `vite.config.ts`) completely intact (`npm run lint`, `npm test`, `npm run build` passing).

---

## Completed Prior Milestones

- **Task 002.1 & Task 002.1A:** Architecture & schema specification (`docs/BACKEND_ARCHITECTURE.md`, `docs/DATABASE_SCHEMA.md`, `docs/API_CONTRACT.md`) finalizing `camelCase` API JSON, `HttpOnly`/`Secure`/`SameSite=Lax` cookie + CSRF auth, advisory line-item reconciliation warnings, and `WORKSPACE_ADMIN`-only soft deletion of unverified invoices.
- **Task 001 – 001.3:** React 19 + TypeScript + Tailwind CSS v4 frontend prototype, Playwright real-Chromium QA (`375px`, `768px`, `1280px` × 6 routes), 11 service unit tests, and initial CI.

---

## Implemented vs. Deferred Breakdown

- **Implemented & Verified in Frontend (`src/`):** React SPA with fictional Indian GST sample data, `localStorage` (`v2`) persistence, CSV formula-safe export, and browser-local file staging (`verify-frontend` passed in CI run `44096786203` and locally).
- **Implemented in `/backend` & `.github/workflows/ci.yml`:** FastAPI service skeleton, `Settings` (`pydantic-settings==2.7.0`), `ApiModel`, `/api/v1/health` & `/api/v1/ready`, SQLAlchemy 2.0 metadata (15 models), Alembic `0001_initial_foundation` (with `op.f(...)` check-constraint naming fix), hardened migration safety guards/tests, constraint-naming & enforcement regression tests, and PostgreSQL 16 CI workflow. In CI run `44096786203` (`783cb7c3`), Python 3.12 compilation, dependency install, `NoDecode`/`Settings` check, and PostgreSQL 16 `alembic upgrade head` succeeded; `pytest -v -ra` passed 38/39 and failed on `test_alembic_upgrade_and_downgrade_on_postgresql` due to the pre-fix double `ck_invoices_` prefix.
- **Pending Re-Run After Sync (`op.f()` CheckConstraint Fix):** Full `pytest -v -ra` suite (including `test_models.py` metadata constraint checks and PostgreSQL 16 `upgrade -> constraint inspection & enforcement -> downgrade -> upgrade` migration cycle) on GitHub Actions CI or a local Python 3.12+ + PostgreSQL 16+ environment.
- **Not Yet Implemented (Task 002.3 Batch 2+):** Cookie auth routes, CSRF guard, RBAC guards, supplier/document/invoice/review endpoints, reporting CSV API, frontend-to-backend integration, and Task 003+ OCR/AI extraction.
