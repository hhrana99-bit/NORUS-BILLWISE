# STATUS — Project Progress

**Current Milestone:** Task 002.4A — Suppliers Master API  
**Status:** Task 002.4A Code & Tests Implemented Locally (on top of verified GitHub `main` CI #14 commit `a873fcb20f98efad1615306d6c73ed9ee16550bc`; `pytest`, Alembic, and PostgreSQL 16 execution pending external Python 3.12+ / GitHub Actions CI run)

---

## Completed Work in Task 002.4A — Suppliers Master API

1. **Suppliers Schemas & Shared Validation (`backend/app/schemas/suppliers.py`, `backend/app/schemas/tenancy.py`)**
   - Added `SupplierCreateRequest`, `SupplierUpdateRequest`, `SupplierDto`, `SupplierSummaryDto`, and `SupplierListResponse` inheriting from `ApiModel` (`camelCase` wire aliases, `extra="forbid"`).
   - Added server-side supplier name cleaning and `normalized_name` computation (trim, collapse repeated whitespace, lowercase) and reused `normalize_and_validate_gstin`, `normalize_and_validate_pan`, and `normalize_and_validate_email` validators with contextual field labels.
   - Enforced `stateCode` 2-digit Indian GST format, `status` validation (`VERIFIED | NEEDS_VERIFICATION | FLAGGED`), non-nullable `PATCH` field rejection (`name`, `category`, `status`), and `NUMERIC -> Decimal` 2-decimal string serialization on `totalValue`.
2. **Suppliers Service & SQL Aggregation (`backend/app/services/supplier_service.py`)**
   - Implemented single-query SQL outer-join invoice statistics (`totalInvoices`, `totalValue`, `lastInvoiceDate`) strictly scoped by `workspace_id` and excluding soft-deleted invoices (`invoices.deleted_at IS NULL`), avoiding N+1 queries.
   - Implemented LIKE-wildcard-escaped case-insensitive search across name, normalized name, GSTIN, PAN, category, state name, and email, plus `status` filtering and deterministic pagination.
   - Enforced workspace-level `normalized_name` uniqueness (`409 SUPPLIER_NAME_EXISTS`) and partial `gstin` uniqueness (`409 SUPPLIER_GSTIN_EXISTS`, allowing multiple `NULL` GSTINs) with pre-checks plus rollback/translation of PostgreSQL `IntegrityError` constraint races (`uq_suppliers_workspace_id_normalized_name`, `uq_suppliers_workspace_gstin`).
   - Emitted workspace-scoped `supplier.created` and `supplier.updated` `audit_events` without logging confidential contact values.
3. **Suppliers FastAPI Router (`backend/app/api/v1/suppliers.py`, `backend/app/api/v1/__init__.py`)**
   - Mounted `GET /api/v1/workspaces/{workspaceId}/suppliers` and `GET /api/v1/workspaces/{workspaceId}/suppliers/{supplierId}` (`WORKSPACE_ADMIN`, `REVIEWER`, `UPLOADER`, `VIEWER`).
   - Mounted `POST /api/v1/workspaces/{workspaceId}/suppliers` and `PATCH /api/v1/workspaces/{workspaceId}/suppliers/{supplierId}` (`WORKSPACE_ADMIN`, `REVIEWER` + `require_csrf`).
   - Preserved uniform `404` responses for foreign workspaces and foreign-workspace `supplierId`s; reused `0001_initial_foundation` `suppliers` table and constraints without adding unnecessary migrations.
4. **Suppliers Unit & PostgreSQL 16 Tests (`backend/tests/test_suppliers.py`)**
   - Added offline schema/normalization tests plus PostgreSQL 16 integration & concurrency tests covering CRUD, search/filtering/pagination, LIKE escaping, normalized-name & GSTIN uniqueness across same vs. separate workspaces, `404` tenant isolation, all 4 RBAC roles (`403` for `VIEWER`/`UPLOADER`), CSRF enforcement, `audit_events` output, SQL aggregate accuracy & soft-delete exclusion, query-count N+1 verification, and `ThreadPoolExecutor` duplicate-creation race handling.

---

## Completed Work in Task 002.2 – 002.3

- **Task 002.3 CI Recovery & README Sync (`125857a` -> `a873fcb`):** Verified GitHub Actions **CI #13 (`44326415648`)** and **CI #14 (`44376162876`) PASS** across both Frontend (`Node 22`: `lint`, `test`, `build`) and Backend (`Python 3.12` + `PostgreSQL 16`: compilation, `alembic upgrade head`, `62` `pytest` tests).
- **Task 002.3 Auth, Tenancy & RBAC:** Core multi-tenant tables (`0001_initial_foundation` + `0002_invites_and_rate_limits`), Argon2id + `HttpOnly` cookie sessions + `Origin`/CSRF + `(IP, account)` PostgreSQL rate limiting + `TRUSTED_PROXIES`, organizations, anti-enumeration invitations, memberships with sole-admin/owner protection and session revocation.
- **Task 001 – 002.2B:** React 19 + TypeScript + Tailwind CSS v4 frontend SPA and FastAPI modular monolith foundation.

---

## Implemented vs. Deferred Breakdown

- **Implemented & Locally Verified (`src/` + frontend tooling):** React 19 SPA with `npm run lint`, `npm test` (`11 passed`), and `npm run build` passing.
- **Implemented in `/backend` (Static Syntax/Bytecode Verified Here; Task 002.4A `pytest`/PostgreSQL 16 `NOT RUN` Locally):** Tasks 002.2, 002.3 (verified via remote GitHub CI #13 & #14), and Task 002.4A Suppliers Master API (`suppliers.py`, `supplier_service.py`, `schemas/suppliers.py`, `tests/test_suppliers.py`).
- **Container Environment Verification Boundary:** Local AI Studio container runs Python `3.11.2` without `pip`, `pytest`, `alembic`, or PostgreSQL 16; live `pytest` execution of `test_suppliers.py` requires running outside the container on Python 3.12+ + PostgreSQL 16+ or via GitHub Actions CI.
- **Not Yet Implemented (Task 002.4B+):** Secure Document Storage & Upload/Streaming (`DocumentStorage`, `POST/GET .../documents`, pinned `python-multipart`), Invoices CRUD + GST/line-item reconciliation + duplicate warnings, Human Review endpoints (`/verify`, `/flag`, `/reopen`), Reporting CSV export, Frontend `WorkspaceContext` API wiring, and Task 003+ OCR/AI extraction.
