# NEXT_TASK — Exact Next Recommended Development Task

## Immediate Verification Prerequisite (Run Outside Container Runtime)

Before starting Task 002.3 feature endpoints, verify the Task 002.2 backend foundation in a standard **Python 3.12+ + PostgreSQL 16+** environment (and sync the repository to GitHub branch `task-001-2-remediation`):

1. Install backend dependencies (`pip install -r backend/requirements.txt`).
2. Run unit & API tests (`cd backend && pytest`).
3. Boot PostgreSQL 16+, set `DATABASE_URL` / `TEST_DATABASE_URL`, run `alembic upgrade head`, run `alembic downgrade base`, run `alembic upgrade head`, and execute `pytest -v` including `test_migrations.py`.
4. Start `uvicorn app.main:app --port 8000` and verify `GET /api/v1/health` (`200`) and `GET /api/v1/ready` (`200`).

---

## Next Development Milestone: NORUS BILLWISE TASK 002.3 — Cookie Authentication, Organizations, Workspaces & RBAC Membership Guards

### Objective
Implement secure browser cookie authentication, session rotation/revocation, CSRF protection, organization/workspace provisioning, and workspace-scoped RBAC dependencies on top of the Task 002.2 `/backend` foundation.

### Deliverables

1. **Password Hashing & Token Security (`app/core/security.py`)**
   - Argon2id password hashing and verification.
   - Short-lived signed `norus_access_token` JWT creation/verification carrying `sub`, `sid`, `org_id`, and token claims.
   - Cryptographically random `norus_refresh_token` generation + SHA-256 hashing (`user_sessions.refresh_token_hash`), token-family rotation (`replaced_by_session_id`), and reuse detection revoking the entire `token_family_id`.
2. **Authentication, Session & CSRF Dependencies (`app/api/v1/auth.py`, `app/core/deps.py`)**
   - Implement `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout`, `POST /api/v1/auth/logout-all`, and `GET /api/v1/auth/me`.
   - Enforce `HttpOnly`, `Secure` (per config), `SameSite=Lax` auth cookies plus double-submit CSRF cookie (`norus_csrf_token`) & `X-CSRF-Token` validation on unsafe HTTP methods (`POST`, `PUT`, `PATCH`, `DELETE`).
   - Never issue bearer tokens for `localStorage`.
3. **Organizations, Workspaces & RBAC Guards (`app/api/v1/workspaces.py`, `app/core/rbac.py`)**
   - Implement `GET /api/v1/workspaces`, `POST /api/v1/workspaces`, `GET /api/v1/workspaces/{workspaceId}/settings`, `PATCH /api/v1/workspaces/{workspaceId}/settings` (`WORKSPACE_ADMIN` only; preserving `require_human_review = true`), and membership management routes.
   - Enforce `WorkspaceContext` authorization (`WORKSPACE_ADMIN`, `REVIEWER`, `UPLOADER`, `VIEWER`) across all tenant-scoped routes and record `audit_events` for login/logout/settings/membership mutations.
4. **Tests & CI**
   - Add `pytest` integration tests covering login, CSRF enforcement, refresh rotation, reuse detection, logout/logout-all revocation, cross-workspace isolation, and role enforcement.
   - Extend `.github/workflows/ci.yml` with a dedicated `backend-ci` job (`PostgreSQL 16` service container, Alembic migration check, and `pytest`).

### Subsequent Tasks (Following Task 002.3)
- **Task 002.4:** Suppliers Master & Secure Document Upload/Storage Service (`DocumentStorage`).
- **Task 002.5:** Invoices CRUD, Flexible Indian GST & Advisory Line-Item Reconciliation Engine, and Advisory Duplicate Detection.
- **Task 002.6:** Human Review Workflow (`/verify`, `/flag`, `/flags/{flagId}/resolve`, `/reopen`, `WORKSPACE_ADMIN` draft soft-delete, immutable `review_actions` & `audit_events`).
- **Task 002.7:** Reporting Aggregations, Formula-Safe CSV Export & Frontend `WorkspaceContext` API Integration (`credentials: 'include'` + `X-CSRF-Token`).
