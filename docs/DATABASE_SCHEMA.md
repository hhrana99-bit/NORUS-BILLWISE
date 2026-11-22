# DATABASE SCHEMA — NORUS BILLWISE

**Database Engine:** PostgreSQL 16+  
**ORM / Migration Tool:** SQLAlchemy 2.0 + Alembic  
**Milestone:** Task 002.5 Implemented on Unified 17-Table Schema *(All 17 tables active in SQLAlchemy models & Alembic migrations `0001`–`0003`; Auth, Tenancy/RBAC, Suppliers, Documents, and Invoices/GST Reconciliation implemented; Human Review & Reports endpoints pending Task 002.6–002.7)*

---

## 1. Schema Conventions & Design Rules

- **Identifier & Column Naming:** All PostgreSQL tables, column names, and SQLAlchemy ORM attributes strictly use `snake_case`. API Pydantic response/request DTOs convert cleanly to `camelCase` at the HTTP boundary.
- **Primary Keys:** `UUID` (`uuid.uuid4` / PostgreSQL `gen_random_uuid()` or Python UUIDv7 for time-ordered index locality).
- **Monetary Precision:** `NUMERIC(14, 2)` across all currency amounts; `NUMERIC(5, 2)` for tax percentages; `NUMERIC(14, 4)` for line-item quantities and unit prices. Floating-point types (`REAL`, `DOUBLE PRECISION`) are prohibited for financial columns.
- **Timestamps:** `TIMESTAMPTZ` stored in UTC (`DEFAULT now()`). Invoice issue/due dates use `DATE` (`YYYY-MM-DD`).
- **Tenant Scoping:** Every workspace-owned table (`suppliers`, `documents`, `invoices`, `invoice_line_items`, `invoice_review_flags`, `review_actions`, `audit_events`) carries an explicit `workspace_id UUID NOT NULL` with composite foreign keys or indexed constraints so tenant filters never rely solely on multi-hop joins.
- **Immutability:** `review_actions` and `audit_events` are append-only; the application database role holds `SELECT` and `INSERT` only (no `UPDATE` or `DELETE` grants). Soft-deletion on `invoices` never deletes related flags, review actions, or audit records.

---

## 2. Entity-Relationship Overview

```text
+------------------+       +-------------------------+       +----------------+
|  organizations   |<------| organization_memberships|------>|     users      |
+--------+---------+       +-------------------------+       +-------+--------+
         |                                                           |
         | 1:N                                                       | 1:N
         v                                                           v
+------------------+       +-------------------------+       +----------------+
|    workspaces    |<------|  workspace_memberships  |       | user_sessions  |
+--------+---------+       +-------------------------+       +----------------+
         |
         +--- 1:1 ---> workspace_settings
         |
         +--- 1:N ---> suppliers
         |
         +--- 1:N ---> documents
         |
         +--- 1:N ---> invoices
         |                |--- 1:N ---> invoice_line_items
         |                |--- 1:N ---> invoice_field_verifications
         |                |--- 1:N ---> invoice_review_flags
         |                +--- 1:N ---> review_actions
         |
         +--- 1:N ---> audit_events
```

---

## 3. Core Entity Specifications

### 3.1 `organizations`
- **Purpose:** Top-level accounting firm or corporate customer account (billing and administrative boundary).
- **Primary Key:** `id` (`UUID`)
- **Foreign Keys:** None
- **Important Fields:**
  - `id UUID PRIMARY KEY`
  - `name VARCHAR(200) NOT NULL`
  - `slug VARCHAR(100) NOT NULL UNIQUE`
  - `firm_type VARCHAR(120) NOT NULL` (e.g., `Chartered Accountancy Practice`)
  - `primary_contact_email VARCHAR(255) NOT NULL`
  - `is_active BOOLEAN NOT NULL DEFAULT TRUE`
  - `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
  - `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- **Relationships:** Has many `workspaces`, `organization_memberships`, and `audit_events`.
- **Constraints:** `UNIQUE (slug)`, `CHECK (char_length(trim(name)) > 0)`.

---

### 3.2 `users`
- **Purpose:** Individual human user account (Partner, CA Reviewer, Staff Uploader, Client Viewer).
- **Primary Key:** `id` (`UUID`)
- **Foreign Keys:** None
- **Important Fields:**
  - `id UUID PRIMARY KEY`
  - `email VARCHAR(255) NOT NULL` (stored normalized lowercase)
  - `full_name VARCHAR(160) NOT NULL`
  - `password_hash VARCHAR(255) NOT NULL` (Argon2id PHC string)
  - `is_active BOOLEAN NOT NULL DEFAULT TRUE`
  - `email_verified_at TIMESTAMPTZ NULL`
  - `last_login_at TIMESTAMPTZ NULL`
  - `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
  - `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- **Relationships:** Has many `organization_memberships`, `workspace_memberships`, `user_sessions`, `review_actions`.
- **Constraints:** Case-insensitive unique index `UNIQUE (lower(email))`.

---

### 3.3 `user_sessions`
- **Purpose:** Server-side revocable session and refresh token store supporting cookie-based auth, rotation chains, token-family reuse detection, and immediate access-cookie revocation (`sid` claim check).
- **Primary Key:** `id` (`UUID` — embedded as `sid` in the `HttpOnly` access JWT cookie)
- **Foreign Keys:**
  - `user_id -> users.id (ON DELETE CASCADE)`
  - `replaced_by_session_id -> user_sessions.id (ON DELETE SET NULL)`
- **Important Fields:**
  - `id UUID PRIMARY KEY`
  - `user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE`
  - `token_family_id UUID NOT NULL`
  - `refresh_token_hash CHAR(64) NOT NULL UNIQUE` (SHA-256 hex digest of `norus_refresh_token` cookie)
  - `replaced_by_session_id UUID NULL REFERENCES user_sessions(id) ON DELETE SET NULL`
  - `ip_address VARCHAR(64) NULL`
  - `user_agent VARCHAR(512) NULL`
  - `expires_at TIMESTAMPTZ NOT NULL`
  - `rotated_at TIMESTAMPTZ NULL`
  - `revoked_at TIMESTAMPTZ NULL`
  - `revoke_reason VARCHAR(120) NULL` (`USER_LOGOUT`, `LOGOUT_ALL`, `ROTATION`, `REFRESH_TOKEN_REUSE_DETECTED`, `ADMIN_REVOKED`)
  - `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- **Constraints:** `INDEX (user_id, revoked_at)`, `INDEX (token_family_id)`, `INDEX (id, revoked_at)`.

---

### 3.4 `workspaces` & `workspace_settings`
- **Purpose:** `workspaces` defines the strict client/ledger tenant boundary; `workspace_settings` stores accounting, GST, buyer identity, and notification preferences (mirroring `WorkspaceSettings` in `src/types/domain.ts`).
- **Primary Key:**
  - `workspaces.id` (`UUID`)
  - `workspace_settings.workspace_id` (`UUID`, 1:1 PK/FK)
- **Foreign Keys:**
  - `workspaces.organization_id -> organizations.id (ON DELETE RESTRICT)`
  - `workspace_settings.workspace_id -> workspaces.id (ON DELETE CASCADE)`
- **Important Fields (`workspaces`):**
  - `id UUID PRIMARY KEY`
  - `organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT`
  - `name VARCHAR(200) NOT NULL`
  - `workspace_code VARCHAR(50) NOT NULL` (e.g., `WS-IN-MUM-001`)
  - `is_active BOOLEAN NOT NULL DEFAULT TRUE`
  - `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
  - `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- **Important Fields (`workspace_settings`):**
  - `workspace_id UUID PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE`
  - `legal_entity_name VARCHAR(240) NOT NULL`
  - `company_gstin VARCHAR(15) NULL`
  - `company_pan VARCHAR(10) NULL`
  - `registered_address TEXT NOT NULL DEFAULT ''`
  - `require_human_review BOOLEAN NOT NULL DEFAULT TRUE`
  - `enable_duplicate_warnings BOOLEAN NOT NULL DEFAULT TRUE`
  - `auto_flag_tax_mismatch BOOLEAN NOT NULL DEFAULT TRUE`
  - `rounding_tolerance NUMERIC(6, 2) NOT NULL DEFAULT 1.00`
  - `default_currency CHAR(3) NOT NULL DEFAULT 'INR'`
  - `financial_year VARCHAR(32) NOT NULL DEFAULT 'April - March'`
  - `date_format VARCHAR(20) NOT NULL DEFAULT 'DD/MM/YYYY'`
  - `tax_regime VARCHAR(64) NOT NULL DEFAULT 'India GST (CGST / SGST / IGST)'`
  - `notify_flagged_invoices BOOLEAN NOT NULL DEFAULT TRUE`
  - `notify_daily_digest BOOLEAN NOT NULL DEFAULT TRUE`
  - `notify_duplicate_alerts BOOLEAN NOT NULL DEFAULT TRUE`
  - `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- **Constraints:**
  - `UNIQUE (organization_id, workspace_code)`
  - `CHECK (require_human_review = TRUE)` — enforces mandatory human review at database level.
  - `CHECK (rounding_tolerance >= 0 AND rounding_tolerance <= 10.00)`

---

### 3.5 `organization_memberships` & `workspace_memberships`
- **Purpose:** Explicit RBAC join tables governing which users belong to an organization and which workspaces they may access and mutate.
- **Primary Key:** `id` (`UUID`) on each table
- **Foreign Keys:**
  - `organization_memberships.organization_id -> organizations.id (ON DELETE CASCADE)`
  - `organization_memberships.user_id -> users.id (ON DELETE CASCADE)`
  - `workspace_memberships.workspace_id -> workspaces.id (ON DELETE CASCADE)`
  - `workspace_memberships.user_id -> users.id (ON DELETE CASCADE)`
  - `workspace_memberships.invited_by_user_id -> users.id (ON DELETE SET NULL)`
- **Important Fields (`workspace_memberships`):**
  - `id UUID PRIMARY KEY`
  - `workspace_id UUID NOT NULL`
  - `user_id UUID NOT NULL`
  - `role VARCHAR(32) NOT NULL` (`WORKSPACE_ADMIN`, `REVIEWER`, `UPLOADER`, `VIEWER`)
  - `status VARCHAR(24) NOT NULL DEFAULT 'ACTIVE'` (`ACTIVE`, `SUSPENDED`)
  - `invited_by_user_id UUID NULL`
  - `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
  - `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- **Constraints:**
  - `UNIQUE (organization_id, user_id)` on `organization_memberships`
  - `UNIQUE (workspace_id, user_id)` on `workspace_memberships`
  - `CHECK (role IN ('WORKSPACE_ADMIN', 'REVIEWER', 'UPLOADER', 'VIEWER'))`
  - Composite unique `(id, workspace_id)` or index on `(user_id, workspace_id, status)` for fast auth dependency checks.

---

### 3.6 `suppliers`
- **Purpose:** Workspace-scoped vendor master directory supporting Indian GSTIN tracking and invoice aggregation.
- **Primary Key:** `id` (`UUID`)
- **Foreign Keys:** `workspace_id -> workspaces.id (ON DELETE CASCADE)`
- **Important Fields:**
  - `id UUID PRIMARY KEY`
  - `workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE`
  - `name VARCHAR(240) NOT NULL`
  - `normalized_name VARCHAR(240) NOT NULL` (lowercased, collapsed whitespace for deterministic matching)
  - `gstin VARCHAR(15) NULL`
  - `pan VARCHAR(10) NULL`
  - `state_code CHAR(2) NULL`
  - `state_name VARCHAR(80) NULL`
  - `category VARCHAR(120) NOT NULL DEFAULT 'General'`
  - `email VARCHAR(255) NULL`
  - `status VARCHAR(32) NOT NULL DEFAULT 'NEEDS_VERIFICATION'` (`VERIFIED`, `NEEDS_VERIFICATION`, `FLAGGED`)
  - `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
  - `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- **Relationships:** Belongs to `workspace`; has many `invoices`.
- **Constraints:**
  - `UNIQUE (workspace_id, normalized_name)`
  - Partial `UNIQUE (workspace_id, gstin) WHERE gstin IS NOT NULL`
  - `UNIQUE (workspace_id, id)` (target for composite tenant FK from `invoices`)
  - `CHECK (status IN ('VERIFIED', 'NEEDS_VERIFICATION', 'FLAGGED'))`

---

### 3.7 `documents`
- **Purpose:** Immutable metadata for uploaded supplier invoice files stored in object storage, decoupling file lifecycle/checksums/virus scanning from accounting records.
- **Primary Key:** `id` (`UUID`)
- **Foreign Keys:**
  - `workspace_id -> workspaces.id (ON DELETE CASCADE)`
  - `uploaded_by_user_id -> users.id (ON DELETE RESTRICT)`
- **Important Fields:**
  - `id UUID PRIMARY KEY`
  - `workspace_id UUID NOT NULL`
  - `uploaded_by_user_id UUID NOT NULL`
  - `original_filename VARCHAR(255) NOT NULL`
  - `storage_key VARCHAR(512) NOT NULL UNIQUE`
  - `mime_type VARCHAR(100) NOT NULL`
  - `byte_size BIGINT NOT NULL`
  - `sha256_checksum CHAR(64) NOT NULL`
  - `page_count INTEGER NOT NULL DEFAULT 1`
  - `scan_status VARCHAR(24) NOT NULL DEFAULT 'PENDING'` (`PENDING`, `CLEAN`, `INFECTED`, `FAILED`, `SKIPPED_DEV`)
  - `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- **Constraints:**
  - `CHECK (byte_size > 0 AND byte_size <= 15728640)`
  - `CHECK (page_count >= 1)`
  - `CHECK (scan_status IN ('PENDING', 'CLEAN', 'INFECTED', 'FAILED', 'SKIPPED_DEV'))`
  - `UNIQUE (workspace_id, id)` (for composite tenant FK from `invoices`)
  - `INDEX (workspace_id, sha256_checksum)` (supports exact binary duplicate detection).

---

### 3.8 `invoices`
- **Purpose:** Core accounting invoice header supporting full Indian GST tax breakup, discounts, cess, freight, round-off, reconciliation status, and mandatory human verification state.
- **Primary Key:** `id` (`UUID`)
- **Foreign Keys:**
  - `workspace_id -> workspaces.id (ON DELETE CASCADE)`
  - `(workspace_id, supplier_id) -> suppliers(workspace_id, id)` (composite tenant-safe FK, nullable for unassigned manual drafts)
  - `(workspace_id, document_id) -> documents(workspace_id, id)` (nullable for seeded/manual entries without file)
  - `verified_by_user_id -> users.id (ON DELETE SET NULL)`
  - `deleted_by_user_id -> users.id (ON DELETE SET NULL)`
- **Important Fields:**
  - `id UUID PRIMARY KEY`
  - `workspace_id UUID NOT NULL`
  - `supplier_id UUID NULL`
  - `document_id UUID NULL`
  - **Supplier & Buyer Snapshots:**
    - `supplier_name_snapshot VARCHAR(240) NOT NULL`
    - `supplier_gstin_snapshot VARCHAR(20) NOT NULL DEFAULT 'PENDING-ENTRY'`
    - `buyer_name_snapshot VARCHAR(240) NOT NULL`
    - `buyer_gstin_snapshot VARCHAR(20) NULL`
    - `place_of_supply_code CHAR(2) NULL`
    - `place_of_supply_name VARCHAR(80) NULL`
  - **Document Metadata:**
    - `invoice_number VARCHAR(100) NOT NULL`
    - `normalized_invoice_number VARCHAR(100) NOT NULL` (lowercased separator-normalized alphanumeric token string computed by `normalize_invoice_number`)
    - `invoice_date DATE NULL`
    - `due_date DATE NULL`
    - `upload_date DATE NOT NULL`
    - `currency CHAR(3) NOT NULL DEFAULT 'INR'`
    - `is_reverse_charge BOOLEAN NOT NULL DEFAULT FALSE`
  - **Flexible Financial Breakdown (`NUMERIC(14, 2)`):**
    - `taxable_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00`
    - `discount_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00`
    - `discount_mode VARCHAR(24) NOT NULL DEFAULT 'NONE'` (`NONE`, `PRE_TAX`, `POST_TAX_COMMERCIAL`)
    - `cgst_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00`
    - `sgst_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00`
    - `igst_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00`
    - `cess_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00`
    - `freight_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00`
    - `other_charges_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00`
    - `round_off_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00` (signed; positive or negative)
    - `total_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00`
  - **Reconciliation, Line-Item Check & Review State:**
    - `computed_expected_total NUMERIC(14, 2) NOT NULL DEFAULT 0.00`
    - `variance_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00`
    - `reconciliation_status VARCHAR(32) NOT NULL DEFAULT 'PENDING_INPUT'` (`MATCHED`, `WITHIN_ROUNDING_TOLERANCE`, `VARIANCE_DETECTED`, `PENDING_INPUT`)
    - `line_items_taxable_sum NUMERIC(14, 2) NULL`
    - `line_item_variance_amount NUMERIC(14, 2) NULL`
    - `line_item_reconciliation_status VARCHAR(32) NOT NULL DEFAULT 'NO_LINE_ITEMS'` (`NO_LINE_ITEMS`, `MATCHED`, `VARIANCE_WARNING`)
    - `line_item_warning TEXT NULL` (advisory warning only; never auto-rejects)
    - `status VARCHAR(24) NOT NULL DEFAULT 'PENDING_REVIEW'` (`PENDING_REVIEW`, `VERIFIED`, `FLAGGED`)
    - `duplicate_warning TEXT NULL`
    - `reviewer_note TEXT NOT NULL DEFAULT ''`
    - `source_type VARCHAR(24) NOT NULL DEFAULT 'MANUAL_UPLOAD'` (`MANUAL_UPLOAD`, `MANUAL_ENTRY`, `OCR_EXTRACTED`, `SEED_DEMO`)
    - `verified_by_user_id UUID NULL`
    - `verified_at TIMESTAMPTZ NULL`
    - `deleted_at TIMESTAMPTZ NULL` (soft delete allowed for `WORKSPACE_ADMIN` on `PENDING_REVIEW` and `FLAGGED` only; forbidden on `VERIFIED`)
    - `deleted_by_user_id UUID NULL`
    - `deletion_reason TEXT NULL`
    - `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
    - `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- **Relationships:** Belongs to `workspace`, optional `supplier`, optional `document`; has many `invoice_line_items`, `invoice_field_verifications`, `invoice_review_flags`, and `review_actions`.
- **Constraints & Indexes:**
  - `UNIQUE (workspace_id, id)` (for child tenant-safe composite FKs)
  - `CHECK (status IN ('PENDING_REVIEW', 'VERIFIED', 'FLAGGED'))`
  - `CHECK (line_item_reconciliation_status IN ('NO_LINE_ITEMS', 'MATCHED', 'VARIANCE_WARNING'))`
  - `CHECK (taxable_amount >= 0 AND discount_amount >= 0 AND cgst_amount >= 0 AND sgst_amount >= 0 AND igst_amount >= 0 AND cess_amount >= 0 AND total_amount >= 0)`
  - `CHECK ((status != 'VERIFIED') OR (verified_by_user_id IS NOT NULL AND verified_at IS NOT NULL))` — enforces that no `VERIFIED` invoice exists without a human verifier reference.
  - `CHECK ((deleted_at IS NULL) OR (status IN ('PENDING_REVIEW', 'FLAGGED')))` — database-level safeguard guaranteeing `VERIFIED` invoices can never be marked soft-deleted.
  - `INDEX (workspace_id, status, invoice_date DESC) WHERE deleted_at IS NULL`
  - `INDEX (workspace_id, supplier_id, normalized_invoice_number) WHERE deleted_at IS NULL`

---

### 3.9 `invoice_line_items`
- **Purpose:** Itemized goods/services lines with HSN/SAC codes, quantities, discounts, and per-line GST breakups.
- **Primary Key:** `id` (`UUID`)
- **Foreign Keys:**
  - `(workspace_id, invoice_id) -> invoices(workspace_id, id) (ON DELETE CASCADE)`
- **Important Fields:**
  - `id UUID PRIMARY KEY`
  - `workspace_id UUID NOT NULL`
  - `invoice_id UUID NOT NULL`
  - `sort_order INTEGER NOT NULL DEFAULT 0`
  - `description TEXT NOT NULL`
  - `hsn_sac VARCHAR(16) NOT NULL DEFAULT ''`
  - `quantity NUMERIC(14, 4) NOT NULL DEFAULT 1.0000`
  - `unit VARCHAR(24) NOT NULL DEFAULT 'NOS'`
  - `unit_price NUMERIC(14, 4) NOT NULL DEFAULT 0.0000`
  - `discount_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00`
  - `taxable_value NUMERIC(14, 2) NOT NULL DEFAULT 0.00`
  - `tax_rate_percent NUMERIC(5, 2) NOT NULL DEFAULT 0.00`
  - `cgst_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00`
  - `sgst_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00`
  - `igst_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00`
  - `cess_amount NUMERIC(14, 2) NOT NULL DEFAULT 0.00`
  - `line_total NUMERIC(14, 2) NOT NULL DEFAULT 0.00`
- **Constraints:** `CHECK (quantity >= 0 AND tax_rate_percent >= 0 AND tax_rate_percent <= 100)`, `INDEX (workspace_id, invoice_id, sort_order)`.

---

### 3.10 `invoice_field_verifications`
- **Purpose:** Normalized replacement for frontend `Invoice.fieldMeta`, recording per-field verification status and source evidence pointers (page + bounding box for Task 003+ OCR).
- **Primary Key:** `id` (`UUID`)
- **Foreign Keys:**
  - `(workspace_id, invoice_id) -> invoices(workspace_id, id) (ON DELETE CASCADE)`
  - `verified_by_user_id -> users.id (ON DELETE SET NULL)`
- **Important Fields:**
  - `id UUID PRIMARY KEY`
  - `workspace_id UUID NOT NULL`
  - `invoice_id UUID NOT NULL`
  - `field_key VARCHAR(48) NOT NULL` (`supplier_name`, `supplier_gstin`, `invoice_number`, `invoice_date`, `due_date`, `taxable_amount`, `discount_amount`, `cgst_amount`, `sgst_amount`, `igst_amount`, `cess_amount`, `freight_amount`, `other_charges_amount`, `round_off_amount`, `total_amount`)
  - `status VARCHAR(24) NOT NULL DEFAULT 'NEEDS_REVIEW'` (`VERIFIED`, `NEEDS_REVIEW`, `FLAGGED`)
  - `evidence_note TEXT NOT NULL DEFAULT ''`
  - `source_page INTEGER NULL`
  - `bounding_box JSONB NULL` (e.g., `{"x": 0.12, "y": 0.24, "w": 0.30, "h": 0.04}`)
  - `confidence_score NUMERIC(4, 3) NULL`
  - `verified_by_user_id UUID NULL`
  - `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- **Constraints:** `UNIQUE (invoice_id, field_key)`, `CHECK (status IN ('VERIFIED', 'NEEDS_REVIEW', 'FLAGGED'))`.

---

### 3.11 `invoice_review_flags`
- **Purpose:** Tracks discrete exception/review flags raised on an invoice (arithmetic variance, duplicate suspicion, GSTIN mismatch, HSN/rate issue, custom CA note) and their resolution lifecycle.
- **Primary Key:** `id` (`UUID`)
- **Foreign Keys:**
  - `(workspace_id, invoice_id) -> invoices(workspace_id, id) (ON DELETE RESTRICT)` (preserved when parent invoice is soft-deleted)
  - `created_by_user_id -> users.id (ON DELETE RESTRICT)`
  - `resolved_by_user_id -> users.id (ON DELETE SET NULL)`
- **Important Fields:**
  - `id UUID PRIMARY KEY`
  - `workspace_id UUID NOT NULL`
  - `invoice_id UUID NOT NULL`
  - `flag_category VARCHAR(64) NOT NULL` (`ARITHMETIC_MISMATCH`, `DUPLICATE_SUSPICION`, `GSTIN_ISSUE`, `HSN_RATE_MISMATCH`, `MISSING_PO_GRN`, `CUSTOM`)
  - `reason_text TEXT NOT NULL`
  - `status VARCHAR(24) NOT NULL DEFAULT 'OPEN'` (`OPEN`, `RESOLVED`, `DISMISSED`)
  - `created_by_user_id UUID NOT NULL`
  - `resolved_by_user_id UUID NULL`
  - `resolution_note TEXT NULL`
  - `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
  - `resolved_at TIMESTAMPTZ NULL`
- **Constraints:** `CHECK (char_length(trim(reason_text)) > 0)`, `CHECK (status IN ('OPEN', 'RESOLVED', 'DISMISSED'))`, `INDEX (workspace_id, invoice_id, status)`.

---

### 3.12 `review_actions`
- **Purpose:** Immutable audit ledger specifically capturing every human review decision, status transition, and explicit arithmetic variance acknowledgment.
- **Primary Key:** `id` (`UUID`)
- **Foreign Keys:**
  - `(workspace_id, invoice_id) -> invoices(workspace_id, id) (ON DELETE RESTRICT)`
  - `actor_user_id -> users.id (ON DELETE RESTRICT)`
- **Important Fields:**
  - `id UUID PRIMARY KEY`
  - `workspace_id UUID NOT NULL`
  - `invoice_id UUID NOT NULL`
  - `actor_user_id UUID NOT NULL`
  - `action_type VARCHAR(32) NOT NULL` (`SAVE_EDITS`, `MARK_VERIFIED`, `VERIFY_WITH_VARIANCE`, `FLAG_INVOICE`, `RESOLVE_FLAG`, `REOPEN_PENDING`)
  - `previous_status VARCHAR(24) NOT NULL`
  - `new_status VARCHAR(24) NOT NULL`
  - `variance_acknowledged BOOLEAN NOT NULL DEFAULT FALSE`
  - `variance_amount_at_action NUMERIC(14, 2) NULL`
  - `comment TEXT NULL`
  - `field_changes JSONB NULL` (before/after snapshot of changed fields)
  - `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- **Constraints:** `INDEX (workspace_id, invoice_id, created_at DESC)`. Append-only.

---

### 3.13 `audit_events`
- **Purpose:** Workspace-wide append-only activity & compliance log powering Dashboard Recent Activity and tenant compliance trails.
- **Primary Key:** `id` (`UUID`)
- **Foreign Keys:**
  - `organization_id -> organizations.id (ON DELETE RESTRICT)`
  - `workspace_id -> workspaces.id (ON DELETE RESTRICT)` (nullable only for org-level events)
  - `actor_user_id -> users.id (ON DELETE SET NULL)`
- **Important Fields:**
  - `id UUID PRIMARY KEY`
  - `organization_id UUID NOT NULL`
  - `workspace_id UUID NULL`
  - `actor_user_id UUID NULL`
  - `actor_display_name VARCHAR(160) NOT NULL`
  - `event_type VARCHAR(64) NOT NULL` (e.g., `auth.login`, `document.uploaded`, `invoice.verified`, `invoice.flagged`, `report.csv_exported`, `membership.updated`)
  - `entity_type VARCHAR(48) NOT NULL` (`invoice`, `document`, `supplier`, `workspace`, `membership`, `report`)
  - `entity_id UUID NULL`
  - `summary TEXT NOT NULL`
  - `tone VARCHAR(16) NOT NULL DEFAULT 'neutral'` (`neutral`, `success`, `warning`)
  - `metadata JSONB NOT NULL DEFAULT '{}'::jsonb`
  - `ip_address VARCHAR(64) NULL`
  - `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- **Constraints:** `CHECK (tone IN ('neutral', 'success', 'warning'))`, `INDEX (workspace_id, created_at DESC)`, `INDEX (organization_id, created_at DESC)`. Append-only.
