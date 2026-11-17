# STATUS — Project Progress

**Current Milestone:** Task 002.3 Batch 2.2 — Critical Remediation & Regression Tests  
**Status:** Batch 2 & Batch 2.2 Implemented Locally (baseline audited CI commit `beec5ff3d28dc5e56ca58244e3c6d4ff586965f1`; Python 3.12 `pytest`, Alembic `0001`–`0002`, and PostgreSQL 16 execution pending GitHub CI)

---

## Completed Work in Task 002.3 Batch 2 – Batch 2.2

1. **Dependencies & Auth/Rate-Limit/Proxy Configuration (`backend/requirements.txt`, `backend/pyproject.toml`, `backend/app/core/config.py`, `backend/.env.example`)**
   - Added `argon2-cffi==23.1.0` and `PyJWT==2.10.1` alongside the verified `pydantic-settings==2.7.0` and `httpx==0.27.2` pins.
   - Added configurable `ACCESS_TOKEN_EXPIRE_MINUTES` (`15`), `REFRESH_TOKEN_EXPIRE_DAYS` (`14`), `JWT_ISSUER`, `JWT_AUDIENCE`, `INVITATION_EXPIRE_HOURS` (`72`), PostgreSQL multi-worker rate-limit settings, and explicit `TRUSTED_PROXIES` (`NoDecode` IP/CIDR allowlist rejecting `*`, `0.0.0.0/0`, and `::/0`).
2. **Core Security, Cookies, Origin/CSRF, Proxy IP & Error Envelope (`backend/app/core/`)**
   - Implemented Argon2id hashing/verification (`memory_cost=65536`, `time_cost=3`, `parallelism=4`), constant-work dummy verification (`dummy_verify_password`), and 12-non-whitespace-character password enforcement.
   - Implemented HS256 short-lived access JWT signing/verification (`sub`, `sid`, `org_id`, `jti`, `typ`, `iss`, `aud`, `iat`, `exp`) and CSPRNG opaque refresh tokens stored exclusively as SHA-256 hex digests in `user_sessions`.
   - Implemented cookie issuance/clearing (`norus_access_token` at `/api/v1`, `norus_refresh_token` at `/api/v1/auth`, readable `norus_csrf_token` at `/`) with `HttpOnly`, `Secure` (per `COOKIE_SECURE`), and `SameSite=Lax`.
   - Implemented `require_allowed_origin` on `/auth/register` & `/auth/login`, `require_csrf`, `get_client_ip` (ignoring `X-Forwarded-For` unless direct peer matches explicit `TRUSTED_PROXIES`, walked safely right-to-left), `get_current_principal`, `require_organization_role`, and `require_workspace_role`.
   - Added global sanitized `SQLAlchemyError`/`Exception` handlers returning standard camelCase `500 INTERNAL_ERROR` with `requestId` plus `Retry-After` header support on `429 RATE_LIMITED`.
3. **Database Migration `0002`, Anti-Enumeration Onboarding & Multi-Worker Concurrency Hardening**
   - Preserved `0001_initial_foundation.py` intact and shortened migration `0002_org_invitations_and_rate_limits.py` revision ID to `0002_invites_and_rate_limits` (`28 <= 32` chars for PostgreSQL `alembic_version.version_num`) with `op.f(...)` check constraints.
   - Added organization membership management (`GET/PATCH/DELETE /organizations/{organizationId}/memberships`) with last-`ORG_OWNER` protection, anti-orphan workspace admin guard (`409 CANNOT_ORPHAN_WORKSPACE_ADMIN` blocking suspension/removal of sole active `WORKSPACE_ADMIN`), and cascade workspace cleanup.
   - Updated invitation list endpoint (`GET /organizations/{organizationId}/invitations`) to return `{ "items": [...] }` matching all collection endpoints, aligned `docs/API_CONTRACT.md` response examples and unimplemented `email_verified_at` documentation, and aligned lock order (`Organization -> OrganizationInvitation`) across invitation creation, revocation, and acceptance.
   - Scoped PostgreSQL login account rate-limit buckets by `(client_ip, normalized_account)` alongside the per-IP limit (`app/services/rate_limit_service.py`) to eliminate cross-IP account-lockout DoS while maintaining multi-worker safety.
4. **Expanded Security & PostgreSQL 16 Concurrency Tests (`backend/tests/`)**
   - Added offline tests for Alembic `<= 32`-char revision IDs & linear history (`test_migrations.py`), `TRUSTED_PROXIES` validation (`test_config.py`), and `get_client_ip` spoof defense (`test_security.py`).
   - Fixed the shadowed `_test_cookie_scope` route in `test_auth_and_tenancy.py` and added PostgreSQL 16 integration/concurrency tests for orphaned-workspace prevention, simultaneous invitation acceptance, invitation creation vs. acceptance races, concurrent duplicate email registration, concurrent duplicate workspace membership creation, cross-IP lockout defense + proxy header handling, and fail-closed rate-limiter DB failures.

---

## Completed Work in Task 002.2 – 002.3 Batch 1

- **Task 002.3 Batch 1 (`66ca811`):** Resolved `pydantic-settings==2.7.0` (`NoDecode`), pinned `httpx==0.27.2`, wrapped all `0001_initial_foundation.py` check constraints in `op.f(...)`, hardened `test_migrations.py` destructive target guards, and configured `verify-backend` PostgreSQL 16 CI (`39 passed` on run `44101659182`).
- **Task 002.2 & 002.2B:** FastAPI `/backend` foundation, SQLAlchemy 2.0 ORM models, Alembic `0001_initial_foundation`, and health/readiness endpoints.
- **Task 001 – 002.1A:** Architecture/API specs and React 19 + TypeScript + Tailwind CSS v4 frontend SPA (`verify-frontend` green).

---

## Implemented vs. Deferred Breakdown

- **Implemented & Locally Verified (`src/` + frontend tooling):** React 19 SPA with `npm run lint`, `npm test`, and `npm run build` passing (`verify-frontend` green on CI `66ca811` and locally).
- **Implemented in `/backend` (Static Syntax/Bytecode Checked Here; Live `pytest`/PostgreSQL 16 `NOT RUN` in Container):** FastAPI service foundation, schema & migrations (`0001` + `0002`), cookie authentication + `Origin`/CSRF + `(IP, account)` multi-worker PostgreSQL rate limiting + `TRUSTED_PROXIES`, organizations/invitations/memberships/workspaces/settings/audit-events endpoints, and Batch 2.2 security & concurrency tests.
- **Container Environment Verification Boundary:** Local AI Studio container runs Python `3.10.12` without `pip`, `pytest`, or PostgreSQL 16; only static Python syntax/bytecode compilation and Node.js frontend checks ran here, while `pytest`, live `alembic upgrade head`, and PostgreSQL 16 integration tests remain `NOT RUN` pending GitHub Actions CI or a local Python 3.12+ + PostgreSQL 16+ host.
- **Not Yet Implemented (Task 002.4+):** Suppliers Master CRUD, secure multipart Document Upload/Streaming (`DocumentStorage`), Invoices CRUD + GST/line-item reconciliation + duplicate warnings, Human Review endpoints (`/verify`, `/flag`, `/reopen`), Reporting CSV export, Frontend `WorkspaceContext` API wiring, and Task 003+ OCR/AI extraction.
