# STATUS — Project Progress

**Current Milestone:** Task 002.3 Batch 1 — Dependency Compatibility, Migration Safety Hardening & PostgreSQL 16 Backend CI  
**Status:** Batch 1 Finalized Locally (`httpx==0.27.2` fix applied after GitHub Actions CI run `44065402657` on `ef44795c956343ac3b6500c38e2b1fd79b196305`; final `pytest` + PostgreSQL 16 CI re-run pending push)

---

## Completed Work in Task 002.3 Batch 1

1. **Dependency Compatibility (`backend/requirements.txt`, `backend/pyproject.toml`, `backend/tests/test_config.py`)**
   - Updated `pydantic-settings` from `2.6.1` to `2.7.0` in both manifests so `from pydantic_settings import NoDecode` in `app/core/config.py` resolves cleanly alongside `pydantic==2.10.3`.
   - Pinned `httpx==0.27.2` in both manifests to match `fastapi==0.115.6` (`starlette<0.42.0`), fixing the `TestClient(app=...)` `TypeError` introduced by `httpx==0.28.1` during CI `pytest` execution.
   - Retained/expanded `test_config.py` regression coverage for comma-separated strings, JSON arrays, direct Python lists, wildcard rejection, and `NoDecode` import verification.
2. **Migration Test Database Safety Hardening (`backend/tests/test_migrations.py`)**
   - Added strict pre-connection guard (`validate_destructive_migration_target`) enforcing PostgreSQL schemes, exact DB name `norus_billwise_test`, approved local/CI hostnames (`localhost`, `127.0.0.1`, `::1`, `postgres`), explicit `NORUS_ALLOW_DESTRUCTIVE_MIGRATION_TEST=1` opt-in, clean skipping when `TEST_DATABASE_URL` is unset, explicit failure under `NORUS_REQUIRE_POSTGRES_TESTS=1`, and credential-free error messages.
   - Added zero-connection unit tests proving production/staging/development/default/`postgres` DB names, remote hosts, malformed URLs, and missing flags fail safely before calling `create_engine` or Alembic.
3. **PostgreSQL 16 GitHub Actions Backend CI (`.github/workflows/ci.yml`)**
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

- **Implemented & Verified in Frontend (`src/`):** React SPA with fictional Indian GST sample data, `localStorage` (`v2`) persistence, CSV formula-safe export, and browser-local file staging (`verify-frontend` passed in CI run `44065402657` and locally).
- **Implemented in `/backend` & `.github/workflows/ci.yml`:** FastAPI service skeleton, `Settings` (`pydantic-settings==2.7.0`), `ApiModel`, `/api/v1/health` & `/api/v1/ready`, SQLAlchemy 2.0 metadata (15 models), Alembic `0001_initial_foundation`, hardened migration safety guards/tests, and PostgreSQL 16 CI workflow. In CI run `44065402657`, Python 3.12 compilation, dependency install, `NoDecode`/`Settings` check, and PostgreSQL 16 `alembic upgrade head` succeeded; `pytest -v -ra` failed before the `httpx==0.27.2` compatibility fix.
- **Pending Re-Run After Sync (`httpx==0.27.2`):** Full `pytest -v -ra` suite (including `TestClient` health/readiness tests and PostgreSQL 16 `upgrade -> downgrade -> upgrade` migration cycle) on GitHub Actions CI or a local Python 3.12+ + PostgreSQL 16+ environment.
- **Not Yet Implemented (Task 002.3 Batch 2+):** Cookie auth routes, CSRF guard, RBAC guards, supplier/document/invoice/review endpoints, reporting CSV API, frontend-to-backend integration, and Task 003+ OCR/AI extraction.
