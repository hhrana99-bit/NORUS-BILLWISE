# NORUS BILLWISE Backend (`/backend`)

**Company:** NORUS AI  
**Product:** NORUS BILLWISE (*Beyond the World.*)  
**Current Milestone:** Task 002.3 Batch 2.2 — Critical Remediation & Regression Tests

---

## 1. Architecture Summary

This directory contains the portable Python FastAPI + PostgreSQL + SQLAlchemy 2.0 + Alembic backend designed in `docs/BACKEND_ARCHITECTURE.md`, `docs/DATABASE_SCHEMA.md`, and `docs/API_CONTRACT.md` (with Task 002.1A finalized decisions).

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
│       ├── 0001_initial_foundation.py
│       └── 0002_org_invitations_and_rate_limits.py
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app factory + request ID + CORS + error handlers
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── health.py        # GET /api/v1/health, GET /api/v1/ready
│   │       ├── auth.py          # Cookie auth: register, login, refresh, logout, logout-all, me
│   │       ├── organizations.py # Organizations CRUD & workspace provisioning
│   │       └── workspaces.py    # Workspaces, settings, memberships & audit-events
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py            # Pydantic BaseSettings & fail-fast security guards
│   │   ├── cookies.py           # Auth/CSRF cookies + Origin/Referer allowlist helpers
│   │   ├── deps.py              # Cookie principal, CSRF, OrganizationContext, WorkspaceContext
│   │   ├── errors.py            # AppError & camelCase ErrorResponse exception handlers
│   │   ├── logging.py           # Structured application logging setup
│   │   └── security.py          # Argon2id hashing, SHA-256 refresh digests, HS256 JWT, CSRF
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py              # DeclarativeBase + deterministic naming convention
│   │   └── session.py           # PostgreSQL engine, sessionmaker, get_db dependency
│   ├── models/
│   │   ├── __init__.py          # Central export for Alembic metadata
│   │   ├── tenancy.py           # organizations, users, user_sessions, workspaces, workspace_settings, memberships
│   │   ├── accounting.py        # suppliers, documents, invoices, invoice_line_items, invoice_field_verifications
│   │   └── review.py            # invoice_review_flags, review_actions, audit_events
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── auth.py              # Auth request/response DTOs (camelCase JSON, zero tokens)
│   │   ├── base.py              # Shared ApiModel & ErrorResponse base schemas
│   │   └── tenancy.py           # Organization, workspace, settings, membership & audit DTOs
│   └── services/
│       ├── __init__.py
│       ├── audit_service.py     # Immutable audit_events emission & workspace-scoped listing
│       ├── auth_service.py      # Argon2id auth, session issuance, refresh rotation & reuse detection
│       ├── rate_limit_service.py # Multi-worker PostgreSQL atomic auth rate-limit buckets
│       └── tenancy_service.py   # Orgs, invitations, memberships, workspaces & deterministic FOR UPDATE locks
└── tests/
    ├── conftest.py
    ├── test_config.py
    ├── test_schemas.py
    ├── test_health_and_app.py
    ├── test_models.py
    ├── test_security.py
    ├── test_auth_and_tenancy.py
    └── test_migrations.py
```

---

## 2. Finalized Architectural & Security Contracts Enforced Here

1. **API JSON Naming (`app/schemas/base.py`) & Error Envelope (`app/core/errors.py`):**
   - Python internals and PostgreSQL columns strictly use `snake_case`; HTTP JSON uses `camelCase` (`alias_generator=to_camel`, `populate_by_name=True`, `extra="forbid"`).
   - Errors return `{ "error": { "code", "message", "details", "requestId" } }` without leaking secrets or stack traces.
2. **Cookie Auth, Origin/CSRF, Multi-Worker Rate Limiting & Token-Family Rotation (`app/core/security.py`, `app/core/cookies.py`, `app/services/auth_service.py`, `app/services/rate_limit_service.py`):**
   - Passwords require at least 12 non-whitespace characters, hashed with Argon2id (`memory_cost=65536`, `time_cost=3`, `parallelism=4`) plus constant-work dummy verification for missing emails.
   - `norus_access_token` (`HttpOnly`, `SameSite=Lax`, `Path=/api/v1`) carries HS256 JWT claims (`sub`, `sid`, `org_id`, `jti`, `typ`, `iss`, `aud`, `iat`, `exp`) and is validated against live unrevoked `user_sessions` rows on every authenticated request.
   - `norus_refresh_token` (`HttpOnly`, `SameSite=Lax`, `Path=/api/v1/auth`) uses CSPRNG secrets stored only as SHA-256 digests (`user_sessions.refresh_token_hash`), rotates on every `/auth/refresh`, and revokes the entire `token_family_id` with a warning audit event if replay of a rotated token is detected.
   - `Origin`/`Referer` allowlist validation protects `/auth/register` and `/auth/login` (rejecting mismatched origins globally and missing `Origin`/`Referer` in `staging`/`production`), while `norus_csrf_token` + `X-CSRF-Token` constant-time verification + `Origin`/`Referer` protect all other unsafe routes.
   - Rate limiting on `/auth/register`, `/auth/login`, and `/auth/refresh` uses atomic PostgreSQL upserts (`auth_rate_limit_buckets`) in isolated committed transactions so limits share reliably across multiple Uvicorn/Gunicorn workers without requiring an external Redis cluster (`429 RATE_LIMITED` + `Retry-After`).
   - Zero tokens are ever returned in JSON bodies or stored in `localStorage`/`sessionStorage`.
3. **Multi-Tenant Isolation, Anti-Enumeration Onboarding & Deterministic Concurrency (`app/core/deps.py`, `app/services/tenancy_service.py`):**
   - Cross-tenant workspace access returns `404 WORKSPACE_NOT_FOUND` (blocking UUID enumeration), and both organization + workspace memberships must be `ACTIVE` along with active parent `Organization`/`Workspace` records.
   - Workspace membership assignment requires active membership in the parent organization, returns one uniform `404 ORGANIZATION_MEMBER_NOT_FOUND` (eliminating global cross-org email enumeration), and is strictly scoped to `WORKSPACE_ADMIN`; legitimate collaborators join via hashed single-use organization invitations (`/organizations/{organizationId}/invitations` + `/organizations/invitations/accept`).
   - Deterministic parent `Organization` / `Workspace` `FOR UPDATE` row locking prevents dual-admin mutation deadlocks while enforcing sole `ORG_OWNER` (`409 CANNOT_DOWNGRADE_LAST_ORG_OWNER`) and sole `WORKSPACE_ADMIN` (`409 CANNOT_DOWNGRADE_LAST_ADMIN`) protection and revoking target user sessions on role/status changes.
   - `require_human_review = true` cannot be disabled (`422 HUMAN_REVIEW_CANNOT_BE_DISABLED`), non-nullable settings reject explicit JSON `null` (`422`), and unhandled errors return a sanitized `500 INTERNAL_ERROR` envelope with `requestId`.

---

## 3. Prerequisites & Local Setup

- **Python:** `3.12+` recommended (`requires-python = ">=3.12"` in `pyproject.toml`)
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
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access JWT lifetime in minutes (default `15`) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh session lifetime in days (default `14`) |
| `JWT_ISSUER` / `JWT_AUDIENCE` | Expected JWT `iss` and `aud` claims |
| `COOKIE_SECURE` | Cookie `Secure` flag (`true` required in staging/production) |
| `CORS_ORIGINS` | Comma-separated string or JSON array of explicit origins (wildcard `*` prohibited) |
| `TRUSTED_PROXIES` | Explicit trusted reverse-proxy IPs or CIDR ranges allowed to supply `X-Forwarded-For` (default empty `[]`) |
| `DOCUMENT_STORAGE_ROOT` | Local filesystem root for document storage adapter (`./var/documents`) |
| `INVITATION_EXPIRE_HOURS` | Organization invitation lifetime in hours (default `72`) |
| `RATE_LIMIT_ENABLED` | Enable PostgreSQL-backed auth rate limiting (default `true`) |
| `RATE_LIMIT_WINDOW_SECONDS` | Fixed window duration in seconds for auth rate limits (default `60`) |
| `LOGIN_RATE_LIMIT_MAX_ATTEMPTS` | Max `/auth/login` attempts per window per IP and `(IP, account)` bucket (default `10`) |
| `REGISTER_RATE_LIMIT_MAX_ATTEMPTS` | Max `/auth/register` attempts per window per IP (default `10`) |
| `REFRESH_RATE_LIMIT_MAX_ATTEMPTS` | Max `/auth/refresh` attempts per window per IP (default `30`) |

### Reverse-Proxy Deployment Note

When running behind Nginx, AWS ALB, Cloud Run, or another L7 reverse proxy, set `TRUSTED_PROXIES` to the exact proxy IP(s) or private subnet CIDR(s) (e.g., `TRUSTED_PROXIES=["10.0.0.0/8"]`). `X-Forwarded-For` is walked right-to-left and ignored unless the immediate TCP peer matches `TRUSTED_PROXIES`. Leaving `TRUSTED_PROXIES` empty disables forwarding-header trust and falls back exclusively to `request.client.host`.

---

## 4. Database Migrations & Running the Server

```bash
cd backend
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

---

## 5. Running Tests (`pytest`) & Safety Controls

Run offline unit, security, config, schema, health/readiness, ORM metadata, and migration guard tests:

```bash
cd backend
pytest -v
```

Run the full suite including live PostgreSQL 16 migrations and auth/tenancy/RBAC integration tests:

```bash
export TEST_DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/norus_billwise_test"
export NORUS_ALLOW_DESTRUCTIVE_MIGRATION_TEST=1
export NORUS_REQUIRE_POSTGRES_TESTS=1
pytest -v -ra
```

Both `test_migrations.py` and `test_auth_and_tenancy.py` validate `TEST_DATABASE_URL` before connecting (`postgresql://`/`postgresql+psycopg://`, approved hosts `localhost`/`127.0.0.1`/`::1`/`postgres`, exact database name `norus_billwise_test`).

---

## 6. Implemented vs. Deferred Scope

- **Implemented in Task 002.2 – 002.3 Batch 2.2:** Config & secrets guards, SQLAlchemy 2.0 ORM models + migrations `0001_initial_foundation` & `0002_invites_and_rate_limits`, PostgreSQL 16 CI workflow, Argon2id + HS256 cookie auth, refresh rotation + token-family reuse detection, `Origin`/CSRF + `(IP, account)` PostgreSQL multi-worker rate limiting + explicit `TRUSTED_PROXIES` handling, organization memberships/invitations (`{ "items": [...] }` envelope + anti-orphan workspace admin guard) + workspaces/settings/memberships/audit-events endpoints, deterministic `FOR UPDATE` lock ordering (`Organization` -> `OrganizationInvitation` / `Workspace` -> `WorkspaceMembership`), and Batch 2.2 security & concurrency regression tests.
- **Not Implemented Yet (Task 002.4+):** Suppliers Master CRUD, Document upload/streaming, Invoices CRUD & GST/reconciliation engine, Human Review workflow (`/verify`, `/flag`, `/reopen`), Reporting CSV export, Frontend-to-Backend API integration, and OCR/AI extraction.
- **Container Environment Note:** Inside the AI Studio container runtime (`Python 3.10.12`, no `pip`, `pytest`, or PostgreSQL server), only static Python syntax/bytecode compilation and Node.js frontend checks ran locally; `pytest`, `alembic upgrade head`, and live PostgreSQL 16 execution remain `NOT RUN` pending remote GitHub Actions CI or a local Python 3.12+ + PostgreSQL 16+ environment.
