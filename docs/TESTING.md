# TESTING — Verification & QA Checklist

## 1. Automated Checks

Run in project root:

```bash
npm ci
npm run lint
npm test
npm run build
```

- `npm ci`: Deterministic clean installation via `npm` using `package-lock.json` (zero peer conflicts, 56 packages audited, 0 vulnerabilities).
- `npm run lint`: Runs `tsc --noEmit` with `strict`, `noUnusedLocals`, `noUnusedParameters`, and `noFallthroughCasesInSwitch`.
- `npm test`: Runs `tsx --test tests/*.test.ts` (11 unit tests) covering:
  - Supplier filtering & normalized matching for locally uploaded invoices (`normalizeSupplierName`, `createDemoUploadedInvoice`)
  - Duplicate warning detection & GST arithmetic mismatch calculation (`detectDuplicateWarning`, `computeArithmeticCheck`)
  - CSV formula injection sanitization (`=`, `+`, `-`, `@`, `\t`, `\r`)
  - Schema-versioned `localStorage` validation & malformed JSON recovery
  - Notification preference filtering (`filterNotificationsBySettings`)
  - Unsaved Review Centre edit detection (`hasUnsavedInvoiceChanges`) across scalars, notes, flag reasons, and per-field statuses
  - Flag reason validation & custom reason resolution (`resolveFlagReason`)
  - Dynamic chronological Monthly Trend reporting (`buildMonthlyTrendStats`, `parseIsoYearMonth`), zero-fill gaps, invalid date skipping, and metric parity
  - Local staged invoice deletion (`removeLocalStagedInvoice`) restrictions
  - Object URL revocation lifecycle (`revokeUnusedBlobUrls`, `revokeAllBlobUrls`)
- `npm run build`: Production Vite bundle build (`vite build`) with route-level chunk splitting and zero Vite config warnings.

## 2. GitHub Actions CI (`.github/workflows/ci.yml`)

- **Triggers:** Pushes and pull requests targeting `main`.
- **Job 1 (`verify-frontend`):** `ubuntu-latest`, Node.js `22` with npm cache -> `npm ci` -> `npm run lint` -> `npm test` -> `npm run build`.
- **Job 2 (`verify-backend`):** `ubuntu-latest`, Python `3.12` + `postgres:16` service container (`norus_billwise_test` with `pg_isready` health check). Installs `backend/requirements.txt`, compiles backend Python modules, verifies `NoDecode` import & `Settings`, runs `alembic upgrade head`, and runs `pytest -v -ra` with `NORUS_REQUIRE_POSTGRES_TESTS=1` and `NORUS_ALLOW_DESTRUCTIVE_MIGRATION_TEST=1` so PostgreSQL migration tests cannot silently skip in CI.

## 3. Backend Automated Tests & Destructive Migration Safety (`backend/tests/`)

Run unit, configuration, schema, health/readiness, ORM metadata, and pre-connection migration safety tests without PostgreSQL:

```bash
cd backend
pytest -v
```

Run live PostgreSQL migration verification (`upgrade -> downgrade -> upgrade`):

```bash
export TEST_DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/norus_billwise_test"
export NORUS_ALLOW_DESTRUCTIVE_MIGRATION_TEST=1
export NORUS_REQUIRE_POSTGRES_TESTS=1
pytest -v -ra
```

- **Why the guard exists:** `test_alembic_upgrade_and_downgrade_on_postgresql` executes `alembic downgrade base`, which drops all database tables.
- **Enforced guardrails (`backend/tests/test_migrations.py`):**
  - Accepts only `postgresql://` or `postgresql+psycopg://` schemes.
  - Requires the exact database name `norus_billwise_test`.
  - Permits only `localhost`, `127.0.0.1`, `::1`, or the CI service hostname `postgres`.
  - Requires explicit `NORUS_ALLOW_DESTRUCTIVE_MIGRATION_TEST=1`.
  - Skips cleanly during ordinary local `pytest` when `TEST_DATABASE_URL` is unset, unless `NORUS_REQUIRE_POSTGRES_TESTS=1` (used in CI) converts missing/unreachable PostgreSQL into an explicit test failure.
  - Note: Real PostgreSQL 16 verification in this environment remains pending execution on GitHub Actions CI or a local Python 3.12+ + PostgreSQL 16+ machine.

## 4. Browser QA Coverage (Executed in Task 001.3 via Playwright Chromium)

- **Viewports Tested:** `375x812` (mobile), `768x1024` (tablet), `1280x800` (desktop) across all 6 routes against `vite preview` (`18` viewport/route states verified for zero page-level horizontal overflow, zero unlabelled visible icon buttons, zero console/page errors, and zero failed internal asset requests).
- **Workflows Verified in Browser:**
  1. Upload modal empty/invalid-type rejection, PDF/PNG staging, and prototype notice clarity.
  2. Invoice search, tax-type filter, column sort, supplier drill-down, and `isLocalUpload`-restricted delete confirmation.
  3. Review Centre 3-action unsaved changes guard (`Continue Editing`, `Discard Changes`, `Save & Continue`), persistent feedback banners, predefined + custom flag reason modal (including blank/whitespace rejection), and arithmetic mismatch verification gate without mutating figures.
  4. Document Preview dynamic Settings buyer details (`legalEntityName`) and PDF `<iframe>` zoom scaling (`100%` -> `115%` -> `130%` -> `115%` -> `100%`) + `URL.revokeObjectURL` cleanup on delete and demo reset.
  5. Dynamic Reports (`6M` vs `All` window switching) and downloaded `.csv` formula neutralization check.
  6. Settings persistence across reload, toggle suppression of duplicate/mismatch/notification triggers, and corrupted `localStorage` recovery.
  7. Mobile (`375px`) drawer/search `Escape` focus return and upload modal focus/keyboard checks.
- **Untested / Demo-Only Limitations:** Native browser `beforeunload` dialog trigger was verified via event listener registration rather than browser unload dismissal; real server upload, OCR/AI extraction, and Excel export remain unimplemented demo boundaries until Task 002.

