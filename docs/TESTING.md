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
- `test_config.py`: `Settings` `NoDecode` CORS and `TRUSTED_PROXIES` CIDR/IP parsing, wildcard/`0.0.0.0/0` rejection, staging/production secret guards.
- `test_schemas.py`: `ApiModel` camelCase serialization and extra-field rejection.
- `test_health_and_app.py`: `/api/v1/health` (`200`), `/api/v1/ready` (`200` connected, `503` redacted).
- `test_models.py`: SQLAlchemy 2.0 metadata parity across all 17 tables (`organization_invitations` and `auth_rate_limit_buckets` included) and PostgreSQL 63-byte identifier bounds.
- `test_security.py`: Argon2id hashing/verification (`m=65536,t=3,p=4`), dummy password check, SHA-256 refresh token digest uniqueness, constant-time CSRF comparison, HS256 JWT claim verification (`sub`, `sid`, `org_id`, `jti`, `iss`, `aud`), expired/tampered/wrong-type rejection, `Origin`/`Referer` staging/production guards, `get_client_ip` trusted-proxy right-to-left validation vs. spoofing rejection, `extra="forbid"`, whitespace password padding (`< 12` non-whitespace chars), GSTIN/PAN/currency/rounding-tolerance/explicit-`null` validation, audit IP 64-char truncation, and sanitized `500 INTERNAL_ERROR` envelope.
- `test_auth_and_tenancy.py` (PostgreSQL 16): Registration + duplicate email (`409`) + concurrent registration race (`[201, 409]`), login (`200`/`401`/`403`) + org-scoped `auth.login` (`workspace_id=None`), `HttpOnly`/`SameSite=Lax`/`Path`/`Secure` cookie flags + non-shadowed `/api/v1` vs `/api/v1/auth` cookie-path scoping + `Max-Age=0` clearing, zero token JSON leakage, `Origin`/`Referer` & CSRF enforcement, expired/tampered JWT cookie rejection, refresh token rotation + token-family replay revocation + `ThreadPoolExecutor` concurrent refresh race, `logout` & `logout-all`, organization/workspace provisioning, anti-enumeration workspace membership rejection (`404 ORGANIZATION_MEMBER_NOT_FOUND`), organization invitation issuance/list (`{ "items": [...] }`)/acceptance/revocation/expiry, concurrent invitation accept & invite-recreation races, org membership suspension/removal revoking workspace access + anti-orphan sole `WORKSPACE_ADMIN` guard (`409 CANNOT_ORPHAN_WORKSPACE_ADMIN`), `is_active=False` `404` hiding, all 4 workspace roles, `ThreadPoolExecutor` dual-admin `FOR UPDATE` & duplicate workspace membership concurrency without deadlocks, last-admin/last-owner `409` protection, cross-IP account-lockout DoS defense + trusted/untrusted proxy integration, rate-limiter DB failure fail-closed `500` check, explicit `null` settings `422`, transaction rollback atomicity, integration URL guard checks, and `requireHumanReview = true` immutability.
- `test_suppliers.py` (Offline Schema Unit Tests + PostgreSQL 16 Integration & Concurrency): Supplier name cleaning & `normalized_name` derivation, GSTIN/PAN/stateCode/email/status validation, `extra="forbid"` immutable-field rejection (`id`, `workspaceId`, `normalizedName`), explicit `null` `PATCH` rejection on non-nullable fields, 2-decimal string serialization of `totalValue`, CRUD lifecycle, search (with `%`/`_` LIKE escaping) & pagination, `status` filter (`422` on unknown status), duplicate normalized-name (`409 SUPPLIER_NAME_EXISTS`) & GSTIN (`409 SUPPLIER_GSTIN_EXISTS`) enforcement (while allowing multiple `NULL` GSTINs and identical names/GSTINs in distinct workspaces), foreign-workspace `404` isolation, RBAC (`WORKSPACE_ADMIN` & `REVIEWER` write vs. `UPLOADER` & `VIEWER` read-only `403`), CSRF enforcement, `audit_events` emission, SQL aggregate accuracy & exclusion of soft-deleted invoices (`deleted_at IS NOT NULL`) + SQL query-count N+1 assertion, and `ThreadPoolExecutor` concurrent duplicate-name and duplicate-GSTIN creation races.
- `test_documents.py` (Offline Unit Tests + PostgreSQL 16 Integration): Blank `document_storage_root` guard, filename/header sanitization (`\r`/`\n`/quotes/traversal/`>255` chars including `'inline; filename="vendor_report_.pdf"'`), `storageKey` omission from DTOs, PDF/PNG/JPEG/WEBP extension + MIME + magic-byte signature validation (`415 UNSUPPORTED_MEDIA_TYPE`), path-traversal & symlink containment rejection, bounded `<= 64 KB` chunk streaming verification, `15 MB` boundary vs. `15 MB + 1` early abort (`413 FILE_TOO_LARGE`), `DocumentUploadSizeLimitMiddleware` pre-multipart `16 MiB` limit (`Content-Length` and unannounced streamed chunks returning single `413 FILE_TOO_LARGE` without affecting other routes), empty file (`422 EMPTY_FILE`), `\x00` NUL-byte rejection on `supplierName`/`invoiceNumber` (`422 VALIDATION_ERROR`), optional draft `PENDING_REVIEW` invoice creation (`createDraftInvoice=true|false`), `document.uploaded` audit emission, DB-failure storage cleanup rollback, RBAC (`WORKSPACE_ADMIN`/`REVIEWER`/`UPLOADER` upload vs. `VIEWER` `403`; all 4 active roles on `CLEAN` download), CSRF enforcement, cross-workspace & intra-org `404` isolation, strict `CLEAN`-only gating (`PENDING`/`SKIPPED_DEV`/`FAILED` -> `409` including PostgreSQL persistence of `FAILED`, `INFECTED` -> `403`, missing disk blob -> `404` without path leakage), `Content-Security-Policy: sandbox` on inline PDFs (`download=false`), and preserved attachment/image headers.
- `test_migrations.py` (PostgreSQL 16 + Pre-Connection Safety Guards):
  - Rejects non-PostgreSQL URLs, non-`norus_billwise_test` database names, unapproved remote hosts, and missing `NORUS_ALLOW_DESTRUCTIVE_MIGRATION_TEST=1` **before** calling `create_engine` or Alembic.
  - Verifies `0001_initial_foundation` -> `0002_invites_and_rate_limits` -> `0003_doc_failed_scan_status` revision IDs fit `alembic_version` `VARCHAR(32)` in a single linear chain, verifies migrations wrap check constraints in `op.f(...)` matching `Base.metadata.tables`, and executes live PostgreSQL `upgrade -> constraint inspection & enforcement (including FAILED/invalid document scan_status) -> downgrade base -> upgrade head`.
- **Container & Remote CI Verification Note:** GitHub Actions **CI #14 (`44376162876`)** passed on `a873fcb`; **CI #15 (`44790860644`)**, **CI #16 (`44795541169`)**, **CI #17 (`44800309064` on `fa89175a`)**, and **CI #18 (`44877773232` on `1adcbdcd`, `5 failed, 92 passed, 1 warning`)** passed Frontend CI (`Node 22`) and failed Backend Step 9 (`pytest -v -ra` on `Python 3.12` + `PostgreSQL 16`). Task 002.4D replaces `status.HTTP_413_CONTENT_TOO_LARGE` with `status.HTTP_413_REQUEST_ENTITY_TOO_LARGE` in `backend/app/main.py` and `backend/app/services/storage_service.py`; static bytecode compilation (`python3 -m compileall`) passed in the container, while full `pytest` and PostgreSQL 16 execution remain `BLOCKED` locally pending Python 3.12 + PostgreSQL 16 or GitHub Actions CI.

## 4. Browser QA Coverage (Executed in Task 001.3 via Playwright Chromium)

- Verified `375x812`, `768x1024`, and `1280x800` viewports across all 6 frontend routes against `vite preview` (zero horizontal overflow, zero console/page errors, zero failed internal asset requests).
- Verified Upload modal, search/filter/sort, Review Centre unsaved-changes guard + flag modal + verification gate, Document Preview PDF zoom & blob URL cleanup, Dynamic Reports + `.csv` formula neutralization, and `localStorage` recovery.
