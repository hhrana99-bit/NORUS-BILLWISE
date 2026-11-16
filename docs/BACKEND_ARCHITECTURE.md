# BACKEND ARCHITECTURE — NORUS BILLWISE

**Company:** NORUS AI  
**Product:** NORUS BILLWISE (*Beyond the World.*)  
**Milestone:** Task 002.1A — Backend Architecture & Database Design (Decisions Finalized)  
**Document Status:** Proposed Target Design (No backend code implemented yet)

---

## 1. Current State vs. Proposed Target Boundary

| Layer / Capability | Current Prototype (Task 001–001.3 Implemented) | Proposed Backend (Task 002.x Target Design) |
| :--- | :--- | :--- |
| **Runtime & Persistence** | React 19 SPA (`WorkspaceContext`) + browser `localStorage` (`schemaVersion: 2`) | React 19 SPA communicating via camelCase REST with Python FastAPI + PostgreSQL 16+ |
| **Data Set** | Fictional Indian GST sample data (`src/data/mockData.ts`) | Multi-tenant relational data scoped strictly by `organization_id` and `workspace_id` |
| **Document Storage** | Browser-local `URL.createObjectURL` blobs (ephemeral per tab) | S3-compatible / local-filesystem object storage abstraction (`Document` metadata in PostgreSQL) |
| **Auth & Tenancy** | Single active workspace preset (`WS-IN-MUM-001`), no login/session | Argon2id credentials, `HttpOnly`/`Secure`/`SameSite` cookie sessions, CSRF protection, revocable refresh rotation, strict RBAC |
| **Invoice Math** | `Taxable + CGST + SGST + IGST === Total` check (`invoiceService.ts`) | Flexible GST + line-item reconciliation (`discount`, `cess`, `freight`, `other_charges`, `round_off`, advisory line-item checks) |
| **Human Review Gate** | Enforced in UI (`requireHumanReview: true`) | Enforced by backend domain rules, API permissions, and immutable `review_actions` |
| **OCR & AI Extraction** | Not implemented (manual entry on local demo staging) | Out of scope for Task 002 core; async worker seam reserved for Task 003+ |

---

## 2. Reconciliation with Existing Documentation

Inspecting `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/NEXT_TASK.md`, and `src/types/domain.ts` revealed three areas where the initial Task 001 target notes must evolve for commercial SaaS readiness:

1. **Simplistic GST Formula (`docs/ARCHITECTURE.md` & ADR-007 vs. Real Invoices):**
   - *Existing Prototype:* `computeArithmeticCheck` assumes `taxableAmount + cgst + sgst + igst === totalAmount`.
   - *Conflict / Gap:* Commercial Indian supplier invoices frequently include GST Compensation Cess, trade/invoice discounts, freight/packaging charges, TCS/other charges, and ±₹1.00 round-off adjustments.
   - *Design Resolution:* Keep the prototype documentation accurate to Task 001 behavior, and introduce a generalized, tolerance-aware Indian GST model in `docs/DATABASE_SCHEMA.md` and Section 5 below. Variances remain **advisory prompts for human confirmation**, never silent edits or auto-approvals.

2. **Flat Workspace Model (`docs/NEXT_TASK.md` vs. Accounting Firm Multi-Tenancy):**
   - *Existing Note:* `docs/NEXT_TASK.md` listed a flat `workspaces` + `users` table list without an `organizations` hierarchy or dedicated `invoice_review_flags` / `review_actions` tables.
   - *Design Resolution:* Introduce `organizations` (accounting practice or enterprise group) above `workspaces` (client GST entity / books), connect users via `organization_memberships` and `workspace_memberships`, and separate mutable open flags (`invoice_review_flags`) from immutable decision history (`review_actions`) and general telemetry (`audit_events`).

3. **Buyer Snapshot Preservation (`src/types/domain.ts` vs. Historical Accuracy):**
   - *Existing Prototype:* `DocumentPreview.tsx` reads buyer details dynamically from `WorkspaceSettings`. If a firm switches legal entity name or GSTIN in Settings, historical invoice previews change retroactively.
   - *Design Resolution:* Persist buyer snapshot columns (`buyer_name`, `buyer_gstin`, `buyer_state_code`, `place_of_supply`) on each `invoices` row at creation/verification time, defaulting from `workspace_settings`.

---

## 3. System Architecture & Component Communication

NORUS BILLWISE targets a **cleanly layered Python FastAPI modular monolith** backed by **PostgreSQL** and portable **object storage**. Keeping the initial backend as a modular monolith minimizes operational complexity while keeping service boundaries ready for async OCR/AI workers in Task 003+.

```text
+-------------------------------------------------------------------------+
|                     React 19 + TypeScript Frontend                      |
|  Pages (Dashboard, Invoices, Review Centre, Suppliers, Reports, Settings)|
|  WorkspaceContext -> API Client (Cookie Credentials + X-CSRF-Token)       |
+------------------------------------+------------------------------------+
                                     | HTTPS / camelCase JSON + multipart
                                     v
+-------------------------------------------------------------------------+
|                         FastAPI Backend (/api/v1)                       |
|  +-------------------------------------------------------------------+  |
|  | API Routers & Auth/Tenant Dependencies                            |  |
|  | - Pydantic v2 (camelCase JSON aliases, snake_case internals)      |  |
|  | - CookieAuthGuard + CSRFGuard + WorkspaceRoleGuard (RBAC)         |  |
|  +---------------------------------+---------------------------------+  |
|                                    v                                    |
|  +-------------------------------------------------------------------+  |
|  | Domain Services Layer (Pure Business Rules, No HTTP Coupling)     |  |
|  | - AuthService      - InvoiceReconciliationService                 |  |
|  | - DuplicateService - ReviewWorkflowService (Human Gate)           |  |
|  | - ReportService    - SafeCsvExportService                         |  |
|  +----------------+--------------------------------+-----------------+  |
|                   |                                |                    |
|                   v                                v                    |
|  +-------------------------------+  +--------------------------------+  |
|  | Repositories (SQLAlchemy 2.0) |  | DocumentStorage Port           |  |
|  | - Explicit workspace_id scope |  | - LocalFSAdapter (Dev)         |  |
|  | - Alembic Schema Migrations   |  | - S3/MinIOAdapter (Prod, FOSS) |  |
|  +---------------+---------------+  +----------------+---------------+  |
+------------------|-----------------------------------|------------------+
                   v                                   v
      +-------------------------+         +-------------------------+
      |    PostgreSQL 16+       |         |  Encrypted Object Store |
      | - UUID PKs, NUMERIC(14,2|         |  PDF / PNG / JPG / WEBP |
      | - Append-only Audit Log |         +------------+------------+
      +------------+------------+                      ^
                   ^                                   |
                   |   (Task 003+ Async Worker Seam)   |
                   +--- [OCR / AI Extraction Worker] --+
                        Proposes field candidates + bounding boxes ONLY.
                        Never sets InvoiceStatus = VERIFIED.
```

### 3.1 Communication Flows

1. **Authentication & Workspace Context Resolution:**
   - Frontend sends credentials to `POST /api/v1/auth/login` (`credentials: 'include'`). FastAPI verifies the Argon2id hash, creates a `user_sessions` row, sets `HttpOnly; Secure; SameSite=Lax` cookies (`norus_access_token` and `norus_refresh_token`) alongside a readable `norus_csrf_token` cookie, and returns non-sensitive user/workspace profile data (no tokens in JSON or `localStorage`).
   - Every tenant request hits `/api/v1/workspaces/{workspaceId}/...`. FastAPI validates the access cookie and active session (`sid`), checks `X-CSRF-Token` on state-changing methods, and verifies active workspace membership and role before any database read or write occurs.
2. **Document Staging & Invoice Creation:**
   - User uploads a PDF/PNG/JPG/WEBP via `POST /api/v1/workspaces/{workspaceId}/documents`.
   - FastAPI validates MIME type, magic bytes, and size, computes SHA-256 checksum, stores the binary via `DocumentStorage` under a generated UUID object key (`orgs/{org_id}/workspaces/{ws_id}/{doc_id}`), inserts a `documents` row, creates a linked `invoices` draft (`status = 'PENDING_REVIEW'`), runs duplicate detection (`DuplicateService`), and logs an `audit_events` entry.
3. **Human Review & Verification Gate:**
   - Reviewer inspects the document stream (`/documents/{documentId}/content`) alongside extracted/entered fields in the Review Centre.
   - Edits via `PATCH /invoices/{invoiceId}` recompute header totals and advisory line-item reconciliation server-side without changing approval state.
   - `POST /invoices/{invoiceId}/verify` requires an authorized human user (`REVIEWER` or `WORKSPACE_ADMIN`), rejects unacknowledged header or line-item variances (`409 VARIANCE_ACKNOWLEDGMENT_REQUIRED` until `confirmVarianceAcknowledgment = true` with note), transitions the invoice to `VERIFIED`, writes an immutable `review_actions` record, and appends to `audit_events`.
4. **Reporting & Formula-Safe CSV Export:**
   - `GET /reports/summary` and `GET /reports/monthly-trend` aggregate PostgreSQL records directly using `DATE_TRUNC('month', invoice_date)` and exact `NUMERIC` sums.
   - `GET /reports/export.csv` streams RFC-4180 CSV with server-side formula-injection sanitization (`=`, `+`, `-`, `@`, `\t`, `\r`) and records an export audit event.

---

## 4. Multi-Tenant Security & Authorization Design

Accounting firms handle multiple unrelated client businesses inside one practice. Data isolation between **Organizations** and between client **Workspaces** is mandatory and enforced exclusively on the backend.

### 4.1 Tenancy Model

- **Organization:** Top-level billing/practice boundary (e.g., *Deshmukh & Associates CA* or a corporate group).
- **Workspace:** Strict accounting data isolation boundary representing one client entity / books / GST ledger. All `suppliers`, `documents`, `invoices`, `invoice_line_items`, `invoice_review_flags`, `review_actions`, and `audit_events` carry `workspace_id`.

### 4.2 Role-Based Access Control (RBAC)

**Organization Roles (`organization_memberships.role`):**
- `ORG_OWNER`: Full billing, organization settings, create/archive workspaces, manage org admins.
- `ORG_ADMIN`: Create/manage client workspaces, assign workspace members, view org-wide directory.
- `ORG_MEMBER`: Standard practice user; accesses only workspaces explicitly granted via `workspace_memberships`.

**Workspace Roles (`workspace_memberships.role`):**

| Capability | `WORKSPACE_ADMIN` | `REVIEWER` | `UPLOADER` | `VIEWER` |
| :--- | :---: | :---: | :---: | :---: |
| View invoices, suppliers, documents, reports | Yes | Yes | Yes | Yes |
| Export CSV reports | Yes | Yes | No | Yes |
| Upload/stage documents & create draft invoices | Yes | Yes | Yes | No |
| Edit invoice accounting fields & line items | Yes | Yes | Drafts only | No |
| Flag invoice / resolve review flags | Yes | Yes | No | No |
| **Mark invoice as `VERIFIED` / Reopen** | **Yes** | **Yes** | **No** | **No** |
| Soft-delete unverified invoice (`PENDING_REVIEW` or `FLAGGED`) | Yes | No | No | No |
| Manage suppliers master | Yes | Yes | No | No |
| Modify workspace settings / GSTIN | Yes | No | No | No |
| Manage workspace memberships | Yes | No | No | No |
| View workspace audit history | Yes | Yes | Own actions | Yes |

*\*Policy note: `WORKSPACE_ADMIN` users may soft-delete unverified `PENDING_REVIEW` and `FLAGGED` invoices via `deleted_at` while preserving the invoice row, `invoice_review_flags`, `review_actions`, and `audit_events`. `VERIFIED` invoices can never be deleted through this draft deletion operation (`409 CANNOT_DELETE_VERIFIED_INVOICE`).*

### 4.3 Multi-Layer Isolation Enforcement

1. **Route & Dependency Gate:** Every workspace endpoint requires `WorkspaceContext = Depends(require_workspace_role(...))` which queries `workspace_memberships` joined to `workspaces` and `organizations` (`is_active = TRUE`), verifying both authentication and membership status.
2. **Repository Query Scoping:** Every SQLAlchemy repository method accepts `workspace_id: UUID` as a non-optional first parameter and includes `.where(Model.workspace_id == workspace_id)`.
3. **Cross-Entity Foreign Key Ownership Verification:** When associating `invoice.supplier_id` or `invoice.document_id`, the service verifies the referenced row belongs to the exact same `workspace_id` before insert/update (preventing IDOR reference linking across tenants).
4. **Uniform Error Semantics:** Requests referencing an existing UUID belonging to a different workspace return `404 Not Found` rather than `403 Forbidden` to prevent cross-tenant existence probing.
5. **PostgreSQL Row-Level Security (Defense-in-Depth):** FastAPI session middleware can execute `SET LOCAL app.current_workspace_id = :ws_id` inside each transaction so PostgreSQL RLS policies reject any accidental unscoped query.

---

## 5. Flexible Indian GST Invoice Data & Verification Model

Real Indian B2B invoices cannot be validated reliably with `Taxable + CGST + SGST + IGST == Total`. NORUS BILLWISE separates **accounting component capture** from **non-destructive arithmetic verification**:

### 5.1 Supported Indian GST Financial Components

- **Base Amounts:** `taxable_amount` (net taxable value per GST rules) and optional `discount_amount` (with `discount_mode`: `NONE`, `PRE_TAX`, or `POST_TAX_COMMERCIAL`).
- **GST Taxes:** `cgst_amount`, `sgst_amount`, `igst_amount`, and `cess_amount` (GST Compensation Cess, applicable to select HSN codes).
- **Additional Non-Tax / Post-Tax Adjustments:** `freight_amount` (un-taxed or separately shown freight/handling), `other_charges_amount` (e.g., TCS under Sec 206C(1H), packing, insurance), and `round_off_amount` (signed `NUMERIC(14, 2)`, positive or negative, typically within ±₹1.00).
- **Final Total & Currency:** `total_amount` (`NUMERIC(14, 2)`), `currency` (`CHAR(3)`, default `'INR'`), plus optional `is_reverse_charge` (`BOOLEAN`) and `due_date` (`DATE`).

### 5.2 Flexible Reconciliation Formula

The backend computes an expected invoice total using explicit `Decimal` arithmetic:

```text
effective_discount = discount_amount if discount_mode == 'POST_TAX_COMMERCIAL' else 0.00
expected_total = (
    taxable_amount
    - effective_discount
    + cgst_amount
    + sgst_amount
    + igst_amount
    + cess_amount
    + freight_amount
    + other_charges_amount
    + round_off_amount
)
variance_amount = total_amount - expected_total
```

*(When `discount_mode == 'PRE_TAX'`, GST is levied on post-discount `taxable_amount`, so `discount_amount` is preserved for audit display without subtracting twice.)*

### 5.3 Verification Outcomes & Human Gate

1. **`MATCHED`:** `abs(variance_amount) == 0.00`. Still remains `PENDING_REVIEW` until human review sign-off.
2. **`WITHIN_ROUNDING_TOLERANCE`:** `0.00 < abs(variance_amount) <= workspace_settings.rounding_tolerance` (e.g., `₹1.00` when `round_off_amount` was not explicitly broken out). Surfaced as an informational note.
3. **`VARIANCE_DETECTED`:** `abs(variance_amount) > tolerance`.
   - If `workspace_settings.auto_flag_tax_mismatch` is enabled, surfaces a warning banner and pre-suggests flagging—never silently edits numbers or rejects ingestion.
   - If a human reviewer confirms the supplier bill reflects commercial adjustments not itemized separately, `POST .../verify` requires `confirmVarianceAcknowledgment = true` and a non-empty `confirmationNote`, recording the variance permanently in `review_actions`.
4. **Line-Item vs. Header Taxable Reconciliation (Advisory):**
   - When an invoice has `line_items.length > 0`, the backend computes `line_items_taxable_sum = SUM(line_items.taxable_value)` and `line_item_variance_amount = taxable_amount - line_items_taxable_sum`.
   - Any discrepancy exceeding `workspace_settings.rounding_tolerance` sets `line_item_reconciliation_status = 'VARIANCE_WARNING'` and populates an advisory `line_item_warning`.
   - **Non-blocking rule:** Line-item discrepancies **never automatically reject** invoice creation or updates. They remain visible in Review Centre and Reports and require human review confirmation (`confirmVarianceAcknowledgment = true`) before `VERIFIED` sign-off when unresolved.
5. **Advisory Tax Regime & GSTIN Checks:**
   - Intra-state (`CGST > 0` or `SGST > 0`) combined with `IGST > 0` triggers an advisory warning (`taxRegimeMismatch`), unless explained/overridden by reviewer.
   - GSTIN format/checksum (`15`-char Indian GSTIN) runs as an advisory validator; placeholder/unregistered suppliers (`URD`) remain inspectable by CAs.
6. **Advisory Duplicate Detection:**
   - Matches within the same `workspace_id` (excluding soft-deleted rows) by: (a) same supplier + normalized `invoice_number` (exact/case-insensitive), or (b) same supplier + `total_amount` within `±₹0.01` + `invoice_date` within 45 days. Always advisory (`duplicate_warning`), never auto-rejected.

---

## 6. Security, Privacy & Operational Controls

- **Password Hashing:** `Argon2id` (`memory_cost=65536`, `time_cost=3`, `parallelism=4`) with per-user cryptographic salt. No plaintext or reversible passwords stored.
- **Cookie-Based Session, CSRF, Rotation & Revocation Strategy:**
  - **Zero Browser Storage of Tokens:** Authentication tokens must **never** be stored in `localStorage` or `sessionStorage`, preventing token exfiltration via XSS scripts.
  - **Access Cookie (`norus_access_token`):** Short-lived signed JWT (`15 min`) carrying `sub` (`user_id`), `sid` (`user_sessions.id`), `jti`, `iat`, `exp` (authorization roles are always loaded fresh from `workspace_memberships`, never cached in the token). Set with `HttpOnly=True`, `Secure=True`, `SameSite=Lax`, `Path=/api/v1`. *(Local plain-HTTP development may toggle `COOKIE_SECURE=false` strictly when `APP_ENV=development` on `localhost`; production startup rejects `COOKIE_SECURE=false`.)*
  - **Refresh Cookie (`norus_refresh_token`):** 256-bit CSPRNG opaque token stored only as a SHA-256 hash in `user_sessions` (`7–14 days`), set with `HttpOnly=True`, `Secure=True`, `SameSite=Lax`, `Path=/api/v1/auth` so it is transmitted only to auth lifecycle endpoints.
  - **CSRF Protection (Mandatory with Cookies):**
    1. All state-changing endpoints (`POST`, `PATCH`, `PUT`, `DELETE`, including `/auth/refresh` and `/auth/logout`) validate a non-`HttpOnly` double-submit CSRF cookie (`norus_csrf_token`, `Secure=True`, `SameSite=Lax`) against the `X-CSRF-Token` request header using constant-time `hmac.compare_digest` (`403 CSRF_TOKEN_INVALID`).
    2. Validate `Origin` / `Referer` headers against `CORS_ORIGINS` (`allow_credentials=True` forbids wildcard `*` origins).
  - **Session Rotation & Reuse Detection:** Every `POST /api/v1/auth/refresh` issues fresh access, refresh, and CSRF cookies, marks the prior `user_sessions` row rotated (`rotated_at`, `replaced_by_session_id`), and stays bound to `token_family_id`. Replaying a previously rotated/revoked refresh token immediately revokes the entire `token_family_id`, emits an `audit_events` security alert, and returns `401`.
  - **Logout & Immediate Session Revocation:** `POST /api/v1/auth/logout` revokes the active `user_sessions` row and clears all three cookies (`Max-Age=0`). `POST /api/v1/auth/logout-all` (and password changes, user deactivation, or membership removals) revokes active `user_sessions`; access-cookie validation checks `sid` revocation state in `user_sessions` (backed by DB/short-TTL lookup) so even active 15-minute access cookies fail immediately upon revocation.
- **API Wire Casing & Input Integrity:** A shared Pydantic `ApiModel` base class configures `alias_generator=to_camel`, `populate_by_name=True`, and `extra="forbid"` so JSON requests and responses match the React TypeScript frontend in `camelCase` while Python internals and SQLAlchemy/PostgreSQL columns remain `snake_case`. All monetary values use `Decimal` / `NUMERIC(14, 2)`—never IEEE-754 floats.
- **File Upload Hardening:**
  - Accepted types strictly enforced by **both** MIME header and binary magic-byte inspection (`%PDF-`, PNG signature, JPEG SOI/EOI, WEBP RIFF/WEBP). Reject mismatched extensions.
  - Size cap (`15 MB` default, configurable via env).
  - Stored using server-generated UUID path keys (`storage_key`) outside the web root; original filename sanitized and stored solely as metadata.
  - Content endpoint streams with `X-Content-Type-Options: nosniff` and strict CSP / `Content-Disposition: inline` (for verified safe PDF/image) or `attachment` download fallback.
  - Designed with `scan_status` (`PENDING`, `CLEAN`, `INFECTED`, `SKIPPED_DEV`) so ClamAV / open-source scanning can gate previews in production.
- **Environment & Secret Management:** All secrets (`DATABASE_URL`, `JWT_SECRET_KEY`, `STORAGE_ROOT`/`S3_ENDPOINT`, `CORS_ORIGINS`) loaded via `pydantic-settings` from environment variables; `.env` remains untracked in `.gitignore`; startup fails fast if production secrets are missing or insecure defaults are used.
- **Audit Logging & Privacy:**
  - `audit_events` captures authentication, membership changes, settings updates, uploads, field edits, flag creations/resolutions, verifications, CSV exports, and draft deletions.
  - Application logs mask GSTIN/PAN tails, email addresses, tokens, and never log invoice binary contents or full financial payloads.
  - Synthetic/fictional Indian GST fixtures only during Tasks 002.x development and automated testing.

---

## 7. Phased Backend Development Plan

Each task below is designed to be small, independently testable via `pytest` + PostgreSQL test fixtures, and mergeable without breaking the existing React frontend:

| Task | Scope & Deliverables | Dependencies | Exit Criteria |
| :--- | :--- | :--- | :--- |
| **Task 002.2** | `/backend` FastAPI app factory, `pydantic-settings`, SQLAlchemy 2.0 base/engine, Alembic setup, `/health` & `/ready` probes, `pytest` + Testcontainers/Postgres fixture setup | Task 002.1 (this design) | `alembic upgrade head` & initial `pytest` health tests pass |
| **Task 002.3** | Core multi-tenant tables (`organizations`, `users`, `user_sessions`, `workspaces`, `workspace_settings`, `memberships`), Auth endpoints (`/auth/*`), Org/Workspace/Membership CRUD & RBAC guards | Task 002.2 | Auth + cross-tenant isolation `pytest` suite (`404` on foreign workspace UUIDs) passes |
| **Task 002.4** | `suppliers` & `documents` tables, `DocumentStorage` interface (`LocalFSAdapter`), secure magic-byte upload & streaming preview endpoints, Supplier CRUD & summary aggregation | Task 002.3 | Upload validation tests (reject spoofed `.exe`/`.txt`), supplier endpoints & tenant checks pass |
| **Task 002.5** | `invoices`, `invoice_line_items`, `invoice_field_verifications` tables, flexible Indian GST reconciliation engine (`Decimal`), duplicate detection service, Invoices CRUD/search/filter/sort | Task 002.4 | Unit + integration tests for discounts, cess, freight, round-off, variance, and search/sort pass |
| **Task 002.6** | `invoice_review_flags`, `review_actions`, `audit_events` tables; `/verify`, `/flag`, `/flags/{id}/resolve`, `/reopen`, `/review-history`, `/audit-events` endpoints; enforced human-review gate | Task 002.5 | Tests verify variance requires confirmation, verified bills reject silent mutation, audit log is append-only |
| **Task 002.7** | Reports endpoints (`/reports/summary`, `/monthly-trend`, `/exceptions`, `/export.csv` with formula sanitization) + React `WorkspaceContext` API client integration & Docker Compose dev stack | Task 002.6 | End-to-end Playwright + FastAPI integration test across all 6 UI routes passes |

---

## 8. Assumptions, Finalized Decisions & Technical Risks

### Assumptions
- Initial launch deploys for Indian GST accounting (`INR`, `CGST/SGST/IGST/Cess`, `DD/MM/YYYY`, April–March FY), while keeping `currency` (`CHAR(3)`) and tax fields extensible for future global expansion.
- Backend and frontend communicate over HTTPS using explicit CORS origin allowlists (`allow_credentials=True`) or behind a single reverse proxy (`/api/v1` routed to FastAPI, `/` routed to the React app).
- Free, open-source infrastructure (`PostgreSQL`, local filesystem or self-hosted `MinIO`, `FastAPI`, `SQLAlchemy`, `Alembic`, `pytest`) satisfies all Task 002 requirements without paid APIs.

### Finalized Architecture Decisions (Task 002.1A)
1. **API JSON Naming (`camelCase` Wire Format / `snake_case` Internals):** FastAPI Pydantic schemas serialize requests and responses in `camelCase` via `alias_generator=to_camel` to match `src/types/domain.ts`, while Python variables, SQLAlchemy models, and PostgreSQL column names remain `snake_case`.
2. **Browser Authentication (`HttpOnly`, `Secure`, `SameSite` Cookies):** Browser sessions use `HttpOnly`, `Secure`, `SameSite=Lax` access (`norus_access_token`) and path-scoped refresh (`norus_refresh_token`) cookies paired with double-submit `norus_csrf_token` + `X-CSRF-Token` validation, refresh rotation with family reuse detection, and immediate `sid`-linked session revocation on `/auth/logout`, `/auth/logout-all`, and security events. Authentication tokens must never be stored in `localStorage`.
3. **Line-Item Reconciliation Policy (Advisory Warning, Non-Blocking):** Discrepancies between invoice header `taxable_amount` and `SUM(invoice_line_items.taxable_value)` produce an advisory `VARIANCE_WARNING` (`lineItemReconciliationStatus` + `lineItemWarning`), never automatically reject an invoice, and require human review/confirmation (`confirmVarianceAcknowledgment`) before `VERIFIED` sign-off.
4. **Draft Deletion Policy (`WORKSPACE_ADMIN` on Unverified Invoices Only):** Authorized `WORKSPACE_ADMIN` users may soft-delete unverified `PENDING_REVIEW` and `FLAGGED` invoices (`deleted_at`, `deleted_by_user_id`, `deletion_reason`). `VERIFIED` invoices can never be deleted through this operation (`409 CANNOT_DELETE_VERIFIED_INVOICE`), and all `invoice_review_flags`, `review_actions`, and `audit_events` remain preserved.

### Remaining Open Implementation Details (To Configure During Task 002.2+)
- **Malware Scanner Integration Timing:** Define whether synchronous ClamAV scanning runs inline inside Task 002.4 uploads or via a local staging flag (`SKIPPED_DEV`) until worker infrastructure lands in Task 003.

### Technical Risks & Mitigations
- **Risk: Cookie Auth Misconfiguration in Local Cross-Port Dev (`:3000` -> `:8000`)** -> *Mitigation:* Proxy `/api/v1` through Vite dev server or configure exact `CORS_ORIGINS` (`http://localhost:3000`) with `allow_credentials=True` and enforce `COOKIE_SECURE=True` in all non-localhost/production environments.
- **Risk: Floating-Point Drift on Monetary Totals** -> *Mitigation:* Enforce `Decimal` in Python and `NUMERIC(14, 2)` in PostgreSQL; serialize currency strings or exact decimals without IEEE-754 floats.
- **Risk: Cross-Tenant Leaks in Complex Joins / Reports** -> *Mitigation:* Mandatory `workspace_id` on every tenant table, repository base scoping, optional PostgreSQL RLS, and automated negative authorization tests for every endpoint.
- **Risk: Sync-to-Async Session Blocking Under File Uploads** -> *Mitigation:* Stream uploads in bounded chunks to `DocumentStorage` rather than buffering entire PDFs in memory; keep heavy OCR/PDF rasterization isolated in Task 003+ background workers.
