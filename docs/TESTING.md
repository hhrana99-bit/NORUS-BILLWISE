# TESTING — Verification & QA Checklist

## 1. Automated Frontend Checks

Run in project root:

```bash
npm ci
npm run lint
npm test
npm run build
```

- `npm ci`: Deterministic clean installation via `npm` using `package-lock.json`.
- `npm run lint`: Runs `tsc --noEmit` with `strict`, `noUnusedLocals`, `noUnusedParameters`, and `noFallthroughCasesInSwitch`.
- `npm test`: Runs `tsx --test tests/*.test.ts` (11 unit tests) covering supplier normalization/filtering, duplicate warning & GST arithmetic mismatch checks, CSV formula neutralization, corrupted `localStorage` recovery, notification filtering, unsaved Review Centre dirty tracking, flag reason resolution, chronological monthly trend stats, local upload delete restrictions, and object URL revocation.
- `npm run build`: Production Vite bundle build (`vite build`) with route-level chunk splitting.

## 2. GitHub Actions CI (`.github/workflows/ci.yml`)

- **Triggers:** Pushes and pull requests targeting `main`.
- **Job 1 (`verify-frontend`):** `ubuntu-latest`, Node.js `22` with npm cache -> `npm ci` -> `npm run lint` -> `npm test` -> `npm run build`.
- **Job 2 (`verify-backend`):** `ubuntu-latest`, Python `3.12` + `postgres:16` service container (`norus_billwise_test` with `pg_isready` health check). Installs `backend/requirements.txt`, compiles backend Python modules (`python -m compileall -q app alembic tests`), verifies `NoDecode` import & `Settings`, runs `alembic upgrade head`, and runs `pytest -v -ra` with `NORUS_REQUIRE_POSTGRES_TESTS=1` and `NORUS_ALLOW_DESTRUCTIVE_MIGRATION_TEST=1`.

## 3. Backend Automated Tests & Destructive Migration Safety (`backend/tests/`)

Run unit, configuration, schema, health/readiness, ORM metadata, cryptography/JWT security, and pre-connection migration safety tests without PostgreSQL (PostgreSQL integration & migration tests skip cleanly when `TEST_DATABASE_URL` is unset):

```bash
cd backend
pytest -v
```

Run the full suite including live PostgreSQL 16 migration checks and auth/tenancy/RBAC API integration tests:

```bash
export TEST_DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/norus_billwise_test"
export NORUS_ALLOW_DESTRUCTIVE_MIGRATION_TEST=1
export NORUS_REQUIRE_POSTGRES_TESTS=1
pytest -v -ra
```

### Coverage Breakdown (`backend/tests/`)
- `test_config.py`: `Settings` `NoDecode` CORS parsing (comma-separated, JSON array, list), wildcard rejection, staging/production secret guards.
- `test_schemas.py`: `ApiModel` camelCase serialization and extra-field rejection.
- `test_health_and_app.py`: `/api/v1/health` (`200`), `/api/v1/ready` (`200` connected, `503` redacted).
- `test_models.py`: SQLAlchemy 2.0 metadata parity and PostgreSQL 63-byte identifier bounds.
- `test_security.py`: Argon2id hashing/verification (`m=65536,t=3,p=4`), dummy password check, SHA-256 refresh token digest uniqueness, constant-time CSRF comparison, HS256 JWT claim verification (`sub`, `sid`, `org_id`, `jti`, `iss`, `aud`), expired/tampered/wrong-type rejection, `Origin` normalization, and immutable `requireHumanReview` schema checks.
- `test_auth_and_tenancy.py` (PostgreSQL 16): Registration + duplicate email (`409`), login (`200`/`401`/`403`), `HttpOnly`/`SameSite=Lax`/`Path`/`Secure` cookie flags, zero token JSON leakage, CSRF & `Origin` enforcement, expired/tampered JWT cookie rejection, refresh token rotation & token-family replay revocation (`auth.refresh_reuse_detected`), `logout` & `logout-all` immediate `sid` revocation, organization/workspace provisioning (`ORG_OWNER`/`ORG_ADMIN`/`ORG_MEMBER`), cross-workspace `404` isolation, all 4 workspace role matrices (`WORKSPACE_ADMIN`, `REVIEWER`, `UPLOADER`, `VIEWER`), last-admin protection (`409 CANNOT_DOWNGRADE_LAST_ADMIN`), immediate session revocation on membership downgrade/suspension/removal, `audit_events` trails, and `requireHumanReview = true` immutability.
- `test_migrations.py` (PostgreSQL 16 + Pre-Connection Safety Guards):
  - Rejects non-PostgreSQL URLs, non-`norus_billwise_test` database names, unapproved remote hosts, and missing `NORUS_ALLOW_DESTRUCTIVE_MIGRATION_TEST=1` **before** calling `create_engine` or Alembic.
  - Verifies `0001_initial_foundation` wraps all check constraints in `op.f(...)` and executes live PostgreSQL `upgrade -> constraint inspection & enforcement -> downgrade base -> upgrade head`.
- **Container Verification Note:** Real `pytest` and PostgreSQL 16 execution of Batch 2 tests requires GitHub Actions CI or a local Python 3.12+ + PostgreSQL 16+ machine; only Python bytecode compilation and Node.js frontend checks can run directly inside the container runtime.

## 4. Browser QA Coverage (Executed in Task 001.3 via Playwright Chromium)

- Verified `375x812`, `768x1024`, and `1280x800` viewports across all 6 frontend routes against `vite preview` (zero horizontal overflow, zero console/page errors, zero failed internal asset requests).
- Verified Upload modal, search/filter/sort, Review Centre unsaved-changes guard + flag modal + verification gate, Document Preview PDF zoom & blob URL cleanup, Dynamic Reports + `.csv` formula neutralization, and `localStorage` recovery.
