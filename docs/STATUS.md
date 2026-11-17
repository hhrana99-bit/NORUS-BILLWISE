# STATUS — Project Progress

**Current Milestone:** Task 002.3 Batch 2 — Authentication, Sessions, Organizations, Workspaces & RBAC  
**Status:** Batch 2 Implemented Locally (baseline CI commit `66ca811927de5483e965c4906a1044028dc3f242`; Python 3.12 `pytest` & PostgreSQL 16 CI execution pending push)

---

## Completed Work in Task 002.3 Batch 2

1. **Dependencies & Auth Configuration (`backend/requirements.txt`, `backend/pyproject.toml`, `backend/app/core/config.py`, `backend/.env.example`)**
   - Added `argon2-cffi==23.1.0` and `PyJWT==2.10.1` alongside the verified `pydantic-settings==2.7.0` and `httpx==0.27.2` pins.
   - Added configurable `ACCESS_TOKEN_EXPIRE_MINUTES` (`15`), `REFRESH_TOKEN_EXPIRE_DAYS` (`14`), `JWT_ISSUER`, and `JWT_AUDIENCE` with startup validation.
2. **Core Security, Cookies, CSRF & Error Envelope (`backend/app/core/`)**
   - Implemented Argon2id hashing/verification (`memory_cost=65536`, `time_cost=3`, `parallelism=4`) plus constant-work dummy verification (`dummy_verify_password`) to prevent timing-based account enumeration.
   - Implemented HS256 short-lived access JWT signing/verification (`sub`, `sid`, `org_id`, `jti`, `typ`, `iss`, `aud`, `iat`, `exp`) and CSPRNG opaque refresh tokens stored exclusively as SHA-256 hex digests in `user_sessions`.
   - Implemented cookie issuance/clearing (`norus_access_token` at `/api/v1`, `norus_refresh_token` at `/api/v1/auth`, readable `norus_csrf_token` at `/`) with `HttpOnly`, `Secure` (per `COOKIE_SECURE`), and `SameSite=Lax`.
   - Implemented `require_csrf` (`Origin`/`Referer` allowlist + constant-time `hmac.compare_digest` double-submit header validation), `get_current_principal` (per-request active `UserSession` `sid` & `revoked_at` check), `require_organization_role`, and `require_workspace_role`.
   - Implemented `AppError` and validation mapping returning the camelCase `ErrorResponse` envelope (including `422 HUMAN_REVIEW_CANNOT_BE_DISABLED`).
3. **Authentication & Multi-Tenant Endpoints + Services (`backend/app/api/v1/`, `backend/app/services/`, `backend/app/schemas/`)**
   - Authentication routes: `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout`, `POST /api/v1/auth/logout-all`, and `GET /api/v1/auth/me`.
   - Refresh rotation uses row-level locking (`SELECT ... FOR UPDATE`), links `replaced_by_session_id`, and revokes the entire `token_family_id` while recording a warning audit event if a rotated token is replayed.
   - Organization & Workspace routes: `GET /api/v1/organizations`, `POST /api/v1/organizations`, `GET /api/v1/workspaces`, `POST /api/v1/organizations/{organizationId}/workspaces`, `GET /api/v1/workspaces/{workspaceId}`, `GET /api/v1/workspaces/{workspaceId}/settings`, `PATCH /api/v1/workspaces/{workspaceId}/settings`, `GET/POST/PATCH/DELETE /api/v1/workspaces/{workspaceId}/memberships`, and `GET /api/v1/workspaces/{workspaceId}/audit-events`.
   - Enforced `404 WORKSPACE_NOT_FOUND` cross-tenant isolation, `require_human_review = true` immutability, `409 CANNOT_DOWNGRADE_LAST_ADMIN` sole-admin protection, immediate session revocation on membership downgrade/suspension/removal, and chronological `audit_events` recording (with `UPLOADER` visibility scoped to own `actor_user_id`).
4. **Security & PostgreSQL Integration Tests (`backend/tests/test_security.py`, `backend/tests/test_auth_and_tenancy.py`)**
   - Added unit tests for Argon2id, SHA-256 refresh digests, constant-time CSRF comparison, HS256 JWT claims/expiry/tampering, origin normalization, and schema validation.
   - Added PostgreSQL integration tests covering registration, login, secure cookie flags, CSRF rejection, access token validation, refresh rotation, token-family replay revocation, logout/logout-all, organization/workspace provisioning, cross-workspace `404` isolation, all 4 workspace roles, last-admin protection, membership session revocation, audit trails, and `requireHumanReview` immutability.

---

## Completed Work in Task 002.2 – 002.3 Batch 1

- **Task 002.3 Batch 1 (`66ca811`):** Resolved `pydantic-settings==2.7.0` (`NoDecode`), pinned `httpx==0.27.2`, wrapped all `0001_initial_foundation.py` check constraints in `op.f(...)`, hardened `test_migrations.py` destructive target guards, and configured `verify-backend` PostgreSQL 16 CI (`39 passed` on run `44101659182`).
- **Task 002.2 & 002.2B:** FastAPI `/backend` foundation, 15 SQLAlchemy 2.0 ORM models, Alembic `0001_initial_foundation`, and health/readiness endpoints.
- **Task 001 – 002.1A:** Architecture/API specs and React 19 + TypeScript + Tailwind CSS v4 frontend SPA (`verify-frontend` green).

---

## Implemented vs. Deferred Breakdown

- **Implemented & Locally Verified (`src/` + frontend tooling):** React 19 SPA with `npm run lint`, `npm test`, and `npm run build` passing (`verify-frontend` green on CI `66ca811` and locally).
- **Implemented in `/backend` (Static Bytecode Checked Here; Live `pytest`/PostgreSQL 16 Pending CI):** FastAPI service foundation, database schema & migrations (`66ca811` green), cookie authentication + CSRF + refresh rotation/reuse detection, organizations/workspaces/settings/memberships/audit-events endpoints, and Batch 2 security/integration tests.
- **Container Environment Verification Boundary:** Local AI Studio container runs Python `3.10.12` without `pip`, `pytest`, or PostgreSQL 16; bytecode compilation (`python3 -m compileall`) passed, while live `pytest` + PostgreSQL 16 execution of Batch 2 tests awaits GitHub Actions CI or a local Python 3.12+ + PostgreSQL 16+ host.
- **Not Yet Implemented (Task 002.4+):** Suppliers Master CRUD, secure multipart Document Upload/Streaming (`DocumentStorage`), Invoices CRUD + GST/line-item reconciliation + duplicate warnings, Human Review endpoints (`/verify`, `/flag`, `/reopen`), Reporting CSV export, Frontend `WorkspaceContext` API wiring, and Task 003+ OCR/AI extraction.
