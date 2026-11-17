# STATUS — Project Progress

**Current Milestone:** Task 002.3 Batch 2.1 — Security Remediation, Reliability & Regression Testing  
**Status:** Batch 2 & Batch 2.1 Implemented Locally (baseline CI commit `66ca811927de5483e965c4906a1044028dc3f242`; Python 3.12 `pytest` & PostgreSQL 16 CI execution pending transfer/push)

---

## Completed Work in Task 002.3 Batch 2 & Batch 2.1

1. **Dependencies & Auth/Rate-Limit Configuration (`backend/requirements.txt`, `backend/pyproject.toml`, `backend/app/core/config.py`, `backend/.env.example`)**
   - Added `argon2-cffi==23.1.0` and `PyJWT==2.10.1` alongside the verified `pydantic-settings==2.7.0` and `httpx==0.27.2` pins.
   - Added configurable `ACCESS_TOKEN_EXPIRE_MINUTES` (`15`), `REFRESH_TOKEN_EXPIRE_DAYS` (`14`), `JWT_ISSUER`, `JWT_AUDIENCE`, `INVITATION_EXPIRE_HOURS` (`72`), and PostgreSQL multi-worker rate-limit settings (`RATE_LIMIT_ENABLED`, `RATE_LIMIT_WINDOW_SECONDS`, `LOGIN_RATE_LIMIT_MAX_ATTEMPTS`, `REGISTER_RATE_LIMIT_MAX_ATTEMPTS`, `REFRESH_RATE_LIMIT_MAX_ATTEMPTS`).
2. **Core Security, Cookies, CSRF/Origin & Error Envelope (`backend/app/core/`)**
   - Implemented Argon2id hashing/verification (`memory_cost=65536`, `time_cost=3`, `parallelism=4`), constant-work dummy verification (`dummy_verify_password`), and 12-non-whitespace-character password enforcement.
   - Implemented HS256 short-lived access JWT signing/verification (`sub`, `sid`, `org_id`, `jti`, `typ`, `iss`, `aud`, `iat`, `exp`) and CSPRNG opaque refresh tokens stored exclusively as SHA-256 hex digests in `user_sessions`.
   - Implemented cookie issuance/clearing (`norus_access_token` at `/api/v1`, `norus_refresh_token` at `/api/v1/auth`, readable `norus_csrf_token` at `/`) with `HttpOnly`, `Secure` (per `COOKIE_SECURE`), and `SameSite=Lax`.
   - Implemented `require_allowed_origin` on `/auth/register` & `/auth/login` (blocking mismatched origins everywhere and missing `Origin`/`Referer` in `staging`/`production`), `require_csrf`, `get_current_principal`, `require_organization_role`, and `require_workspace_role` (enforcing active `OrganizationMembership` + active `Organization` + active `Workspace` + active `WorkspaceMembership`).
   - Added global sanitized `SQLAlchemyError`/`Exception` handlers returning standard camelCase `500 INTERNAL_ERROR` with `requestId` plus `Retry-After` header support on `429 RATE_LIMITED`.
3. **Database Migration `0002`, Anti-Enumeration Onboarding & Multi-Worker Concurrency Hardening**
   - Preserved `0001_initial_foundation.py` intact and added `0002_org_invitations_and_rate_limits.py` (`organization_invitations`, `auth_rate_limit_buckets`) with `op.f(...)` check constraints.
   - Added organization membership management (`GET/PATCH/DELETE /organizations/{organizationId}/memberships`) with last-`ORG_OWNER` protection and cascade workspace cleanup, plus anti-enumeration organization invitations (`/organizations/{organizationId}/invitations` and `/organizations/invitations/accept`).
   - Updated `POST /workspaces/{workspaceId}/memberships` to require active organization membership and return one uniform `404 ORGANIZATION_MEMBER_NOT_FOUND` (eliminating cross-org email enumeration and unconsented cross-org binding).
   - Added PostgreSQL atomic rate-limit buckets (`app/services/rate_limit_service.py`) in isolated committed transactions (multi-worker safe without requiring Redis), deterministic parent `Organization`/`Workspace` `FOR UPDATE` lock ordering eliminating dual-admin deadlocks, clean `IntegrityError` -> `409` conflict handling, explicit `null` `422` rejection on non-nullable settings, Indian GSTIN/PAN validation, 64-char audit IP truncation, and org-scoped `auth.login` audit events (`workspace_id=None`).
4. **Expanded Security & PostgreSQL 16 Concurrency Tests (`backend/tests/`)**
   - Updated `test_models.py` & `test_migrations.py` (`17` tables; multi-migration `op.f(...)` AST parity) and expanded `test_security.py` & `test_auth_and_tenancy.py` with unit + PostgreSQL 16 integration tests for anti-enumeration onboarding, org suspension revocation, staging/production `Origin`/`Referer` guards, PostgreSQL rate limiting (`429` + `Retry-After`), `ThreadPoolExecutor` concurrent dual-admin/refresh races, explicit `null` settings `422`, transaction rollback atomicity, and `500 INTERNAL_ERROR` sanitization.

---

## Completed Work in Task 002.2 – 002.3 Batch 1

- **Task 002.3 Batch 1 (`66ca811`):** Resolved `pydantic-settings==2.7.0` (`NoDecode`), pinned `httpx==0.27.2`, wrapped all `0001_initial_foundation.py` check constraints in `op.f(...)`, hardened `test_migrations.py` destructive target guards, and configured `verify-backend` PostgreSQL 16 CI (`39 passed` on run `44101659182`).
- **Task 002.2 & 002.2B:** FastAPI `/backend` foundation, SQLAlchemy 2.0 ORM models, Alembic `0001_initial_foundation`, and health/readiness endpoints.
- **Task 001 – 002.1A:** Architecture/API specs and React 19 + TypeScript + Tailwind CSS v4 frontend SPA (`verify-frontend` green).

---

## Implemented vs. Deferred Breakdown

- **Implemented & Locally Verified (`src/` + frontend tooling):** React 19 SPA with `npm run lint`, `npm test`, and `npm run build` passing (`verify-frontend` green on CI `66ca811` and locally).
- **Implemented in `/backend` (Static Syntax/Bytecode Checked Here; Live `pytest`/PostgreSQL 16 `NOT RUN` in Container):** FastAPI service foundation, schema & migrations (`0001` + `0002`), cookie authentication + `Origin`/CSRF + multi-worker PostgreSQL rate limiting, organizations/invitations/memberships/workspaces/settings/audit-events endpoints, and Batch 2.1 security/concurrency tests.
- **Container Environment Verification Boundary:** Local AI Studio container runs Python `3.10.12` without `pip`, `pytest`, or PostgreSQL 16; only static Python syntax/bytecode compilation and Node.js frontend checks ran here, while `pytest`, live `alembic upgrade head`, and PostgreSQL 16 integration tests remain `NOT RUN` pending GitHub Actions CI or a local Python 3.12+ + PostgreSQL 16+ host.
- **Not Yet Implemented (Task 002.4+):** Suppliers Master CRUD, secure multipart Document Upload/Streaming (`DocumentStorage`), Invoices CRUD + GST/line-item reconciliation + duplicate warnings, Human Review endpoints (`/verify`, `/flag`, `/reopen`), Reporting CSV export, Frontend `WorkspaceContext` API wiring, and Task 003+ OCR/AI extraction.
