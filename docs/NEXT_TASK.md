# NEXT_TASK — Exact Next Recommended Development Task

## Immediate Repository Hygiene Note

- Ensure Task 001.3 + Task 002.1/002.1A documentation changes (`docs/BACKEND_ARCHITECTURE.md`, `docs/DATABASE_SCHEMA.md`, `docs/API_CONTRACT.md`, `.github/workflows/ci.yml`) are synced to GitHub branch `task-001-2-remediation` (confirming `bun.lock` remains ignored/uncommitted) and verify **Frontend CI** passes.

---

## Next Development Milestone: NORUS BILLWISE TASK 002.2 — Backend Service Skeleton, Database Engine & Migrations

### Objective
Bootstrap the portable `/backend` Python FastAPI + PostgreSQL + SQLAlchemy 2.0 + Alembic foundation matching the finalized Task 002.1A design in `docs/BACKEND_ARCHITECTURE.md`, `docs/DATABASE_SCHEMA.md`, and `docs/API_CONTRACT.md`, without altering the existing frontend or enabling autonomous invoice approval.

### Deliverables

1. **FastAPI Application Structure (`/backend`)**
   - Create modular package layout: `app/core/config.py` (`pydantic-settings`), `app/core/logging.py`, `app/schemas/base.py` (shared `ApiModel` with `camelCase` alias generation and `snake_case` Python attributes), `app/db/session.py`, `app/db/base.py`, `app/main.py`, `tests/`.
   - Add backend `.env.example` (`DATABASE_URL`, `JWT_SECRET_KEY`, `DOCUMENT_STORAGE_ROOT`, `CORS_ORIGINS`, `COOKIE_SECURE`) with zero hardcoded secrets.
   - Add `pyproject.toml` / `requirements.txt` pinned cleanly for reproducible installs (`fastapi`, `uvicorn`, `sqlalchemy`, `psycopg[binary]`, `alembic`, `pydantic-settings`, `pytest`, `httpx`).
2. **PostgreSQL & Alembic Migrations**
   - Configure Alembic (`alembic.ini`, `alembic/env.py`) against `snake_case` SQLAlchemy 2.0 declarative metadata.
   - Author initial migration (`0001_initial_foundation`) creating core tenancy & identity tables (`organizations`, `users`, `user_sessions` with rotation/revocation columns, `workspaces`, `workspace_settings`, `organization_memberships`, `workspace_memberships`), `suppliers`, `documents`, `invoices` (including flexible Indian GST, advisory line-item reconciliation, and audit-safe soft-delete columns/constraints), `invoice_line_items`, `invoice_field_verifications`, `invoice_review_flags`, `review_actions`, and `audit_events`.
3. **Health Endpoints, CI & Tests**
   - Implement `GET /api/v1/health` (liveness) and `GET /api/v1/ready` (database connectivity check).
   - Add automated `pytest` tests verifying configuration validation, `ApiModel` `camelCase` serialization, health/readiness probes, and clean migration upgrade/downgrade against PostgreSQL.
   - Extend GitHub Actions CI with a backend verification job (`ruff` / `mypy` / `pytest`) alongside existing Frontend CI.

### Subsequent Tasks (Following Task 002.2)
- **Task 002.3:** Cookie Authentication (`HttpOnly`/`Secure`/`SameSite`, CSRF guard, refresh rotation, logout/logout-all, Argon2id), Organizations, Workspaces & RBAC Membership guards.
- **Task 002.4:** Suppliers Master & Secure Document Upload/Storage Service.
- **Task 002.5:** Invoices CRUD, Flexible Indian GST & Advisory Line-Item Reconciliation Engine, and Advisory Duplicate Detection.
- **Task 002.6:** Human Review Workflow (`/verify`, `/flag`, `/flags/{flagId}/resolve`, `/reopen`, `WORKSPACE_ADMIN` draft soft-delete, immutable `review_actions` & `audit_events`).
- **Task 002.7:** Reporting Aggregations, Formula-Safe CSV Export & Frontend `WorkspaceContext` API Integration (`credentials: 'include'` + `X-CSRF-Token`, zero tokens in `localStorage`).


