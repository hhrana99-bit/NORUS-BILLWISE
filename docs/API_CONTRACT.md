# API CONTRACT — NORUS BILLWISE

**API Prefix:** `/api/v1`  
**Framework:** FastAPI + Pydantic v2  
**Milestone:** Task 002.1A — Proposed REST API Specification (Finalized Decisions; Not yet implemented)

---

## 1. Global API Conventions

- **Content Type:** `application/json` (except document uploads via `multipart/form-data`, file downloads via binary stream, and CSV export via `text/csv; charset=utf-8`).
- **Field Naming (`camelCase` Wire Format):** All JSON request payloads, JSON response payloads, query parameters, and multipart form fields use **`camelCase`** to match the React TypeScript frontend (`src/types/domain.ts`). Python internal variables, SQLAlchemy ORM fields, and PostgreSQL database columns remain `snake_case` via a shared Pydantic `ApiModel` base (`alias_generator=to_camel`, `populate_by_name=True`, `extra="forbid"`).
- **Monetary Values:** Serialized as fixed 2-decimal strings (e.g., `"147500.00"`) or exact decimal strings to prevent JavaScript IEEE-754 floating-point drift.
- **Browser Cookie Authentication & CSRF Protection:**
  - Authentication relies strictly on secure cookies (`norus_access_token` with `HttpOnly; Secure; SameSite=Lax; Path=/api/v1`, and `norus_refresh_token` with `HttpOnly; Secure; SameSite=Lax; Path=/api/v1/auth`).
  - **Tokens are never returned in JSON response bodies and must never be stored in `localStorage` or `sessionStorage`.** Frontend requests pass `credentials: 'include'`.
  - Every state-changing request (`POST`, `PATCH`, `PUT`, `DELETE`) other than `/auth/login` and `/auth/register` requires a matching `X-CSRF-Token` header paired with the `norus_csrf_token` cookie (plus strict `Origin` / `Referer` validation against configured `CORS_ORIGINS`).
- **Tenant Isolation Rule:** Every workspace endpoint carries `{workspaceId}` in the path. Requests for a `workspaceId` or child resource outside the authenticated user's active memberships return `404 Not Found` (preventing cross-tenant UUID enumeration).
- **Standard Error Envelope:**

```json
{
  "error": {
    "code": "VARIANCE_ACKNOWLEDGMENT_REQUIRED",
    "message": "Invoice or line-item reconciliation variance requires explicit human confirmation before verification.",
    "details": {
      "varianceAmount": "1000.00",
      "computedExpectedTotal": "54870.00",
      "declaredTotal": "55870.00",
      "lineItemVarianceAmount": "0.00"
    },
    "requestId": "req_01J9X7K2..."
  }
}
```

---

## 2. Authentication Endpoints

### `POST /api/v1/auth/register`
- **Purpose:** Register a new user account and optionally bootstrap an initial Organization + Workspace, setting authentication and CSRF cookies.
- **Auth:** Public (rate-limited).
- **Request Body:**
  ```json
  {
    "email": "ananya@deshmukhca.example",
    "password": "StrongPassword!123",
    "fullName": "CA Ananya Deshmukh",
    "organizationName": "Deshmukh & Associates CA",
    "firmType": "Chartered Accountancy Practice"
  }
  ```
- **Response (`201 Created`):** User profile and initial organization/workspace summary (no tokens in body); sets `Set-Cookie` for `norus_access_token`, `norus_refresh_token`, and `norus_csrf_token`.
- **Errors:** `409 EMAIL_ALREADY_EXISTS`, `422 VALIDATION_ERROR`.

### `POST /api/v1/auth/login`
- **Purpose:** Authenticate user via Argon2id password check, create a `user_sessions` record, and issue `HttpOnly` access/refresh cookies plus `norus_csrf_token`.
- **Auth:** Public (rate-limited).
- **Request Body:** `{ "email": "...", "password": "..." }`
- **Response (`200 OK`):**
  ```json
  {
    "user": { "id": "uuid", "email": "...", "fullName": "CA Ananya Deshmukh" },
    "workspaces": [
      { "workspaceId": "uuid", "name": "Deshmukh & Associates CA", "workspaceCode": "WS-IN-MUM-001", "role": "WORKSPACE_ADMIN" }
    ],
    "sessionExpiresAt": "2026-11-30T10:30:00Z"
  }
  ```
  Sets `Set-Cookie` headers (`norus_access_token`, `norus_refresh_token`, `norus_csrf_token`).
- **Errors:** `401 INVALID_CREDENTIALS`, `403 ACCOUNT_DISABLED`, `429 RATE_LIMITED`.

### `POST /api/v1/auth/refresh`
- **Purpose:** Validate and rotate the `norus_refresh_token` cookie, create a linked replacement `user_sessions` row, revoke the previous refresh row (`rotated_at`), and issue fresh access, refresh, and CSRF cookies.
- **Auth:** Refresh cookie (`norus_refresh_token`) + `X-CSRF-Token` header.
- **Response (`200 OK`):** `{ "refreshed": true, "sessionExpiresAt": "2026-11-30T10:45:00Z" }` + rotated `Set-Cookie` headers.
- **Errors:** `401 SESSION_EXPIRED_OR_REVOKED` (triggers full token-family revocation if replay of a rotated token is detected), `403 CSRF_TOKEN_INVALID`.

### `POST /api/v1/auth/logout`
- **Purpose:** Revoke current `user_sessions` row (`USER_LOGOUT`), immediately invalidate the `sid`-linked access cookie, and expire all three cookies (`Max-Age=0`).
- **Auth:** Access cookie (`norus_access_token`) and/or refresh cookie + `X-CSRF-Token` header.
- **Response (`204 No Content`)**

### `POST /api/v1/auth/logout-all`
- **Purpose:** Revoke all active `user_sessions` rows for the authenticated user (`LOGOUT_ALL`), terminating sessions across all devices and clearing local cookies.
- **Auth:** Access cookie + `X-CSRF-Token` header.
- **Response (`204 No Content`)**

### `GET /api/v1/auth/me`
- **Purpose:** Return authenticated user profile and active organization/workspace memberships so the SPA can hydrate session state without reading cookies or `localStorage`.
- **Auth:** Valid access cookie (`norus_access_token` with non-revoked `sid`).
- **Response (`200 OK`):** User summary + `organizations[]` + `workspaces[]` with roles.

---

## 3. Organizations & Workspaces Endpoints

### `GET /api/v1/organizations`
- **Purpose:** List organizations where the current user holds an active membership.
- **Auth:** Authenticated user.
- **Response (`200 OK`):** `{ "items": [{ "id": "uuid", "name": "...", "slug": "...", "firmType": "...", "role": "ORG_OWNER" }] }`.

### `POST /api/v1/organizations`
- **Purpose:** Create a new accounting firm or enterprise organization and assign creator as `ORG_OWNER`.
- **Auth:** Authenticated user + CSRF.
- **Request Body:** `{ "name": "...", "firmType": "...", "primaryContactEmail": "..." }`
- **Response (`201 Created`):** Created organization DTO.

### `GET /api/v1/workspaces`
- **Purpose:** List all active workspaces accessible to the authenticated user (filterable by `organizationId`).
- **Auth:** Authenticated user.
- **Response (`200 OK`):** `{ "items": [{ "id": "uuid", "organizationId": "uuid", "name": "...", "workspaceCode": "...", "role": "REVIEWER" }] }`.

### `POST /api/v1/organizations/{organizationId}/workspaces`
- **Purpose:** Create a new client workspace + default `workspace_settings` (`requireHumanReview = true`).
- **Auth:** `ORG_OWNER` or `ORG_ADMIN` of `{organizationId}` + CSRF.
- **Request Body:** `{ "name": "...", "workspaceCode": "...", "legalEntityName": "...", "companyGstin": "..." }`
- **Response (`201 Created`):** Workspace + settings DTO.

### `GET /api/v1/workspaces/{workspaceId}`
- **Purpose:** Fetch workspace metadata and caller's effective role.
- **Auth:** Any active workspace member.
- **Response (`200 OK`):** Workspace summary + `currentUserRole`.

### `GET /api/v1/workspaces/{workspaceId}/settings`
- **Purpose:** Retrieve `workspace_settings` (firm details, GST preferences, duplicate/mismatch toggles, rounding tolerance, notifications).
- **Auth:** Any active workspace member.
- **Response (`200 OK`):** Settings DTO matching `WorkspaceSettings` fields plus `roundingTolerance`.

### `PATCH /api/v1/workspaces/{workspaceId}/settings`
- **Purpose:** Update editable workspace settings. Backend rejects attempts to set `requireHumanReview = false`.
- **Auth:** `WORKSPACE_ADMIN` + CSRF.
- **Request Body:** Partial settings update (`legalEntityName`, `companyGstin`, `enableDuplicateWarnings`, `autoFlagTaxMismatch`, `roundingTolerance`, `notifyFlaggedInvoices`, `notifyDailyDigest`, `notifyDuplicateAlerts`).
- **Response (`200 OK`):** Updated settings DTO (`requireHumanReview` always `true`).
- **Errors:** `422 HUMAN_REVIEW_CANNOT_BE_DISABLED`.

---

## 4. Users & Workspace Memberships Endpoints

### `GET /api/v1/workspaces/{workspaceId}/memberships`
- **Purpose:** List members and roles assigned to the workspace.
- **Auth:** `WORKSPACE_ADMIN`, `REVIEWER`, `VIEWER`.
- **Response (`200 OK`):** `{ "items": [{ "id": "uuid", "userId": "uuid", "email": "...", "fullName": "...", "role": "REVIEWER", "status": "ACTIVE" }] }`.

### `POST /api/v1/workspaces/{workspaceId}/memberships`
- **Purpose:** Add an existing organization user (or invite by email) to the workspace with an explicit role.
- **Auth:** `WORKSPACE_ADMIN` (or `ORG_ADMIN`) + CSRF.
- **Request Body:** `{ "email": "staff@deshmukhca.example", "role": "REVIEWER" }`
- **Response (`201 Created`):** Membership DTO.
- **Errors:** `409 MEMBERSHIP_ALREADY_EXISTS`.

### `PATCH /api/v1/workspaces/{workspaceId}/memberships/{membershipId}`
- **Purpose:** Update a member's `role` or `status` (`ACTIVE` / `SUSPENDED`) and revoke active user sessions if suspended or downgraded.
- **Auth:** `WORKSPACE_ADMIN` + CSRF.
- **Request Body:** `{ "role": "VIEWER", "status": "ACTIVE" }`
- **Response (`200 OK`):** Updated membership DTO.
- **Errors:** `409 CANNOT_DOWNGRADE_LAST_ADMIN`.

### `DELETE /api/v1/workspaces/{workspaceId}/memberships/{membershipId}`
- **Purpose:** Remove user access to the workspace (revokes target sessions for the workspace and prevents removing the sole remaining `WORKSPACE_ADMIN`).
- **Auth:** `WORKSPACE_ADMIN` + CSRF.
- **Response (`204 No Content`)**

---

## 5. Suppliers Endpoints

### `GET /api/v1/workspaces/{workspaceId}/suppliers`
- **Purpose:** Search/filter suppliers with aggregated `totalInvoices`, `totalValue`, and `lastInvoiceDate` (excluding soft-deleted invoices).
- **Auth:** Any active workspace member.
- **Query Params:** `search`, `status` (`VERIFIED|NEEDS_VERIFICATION|FLAGGED`), `page`, `pageSize`.
- **Response (`200 OK`):** `{ "items": [...], "total": 6, "page": 1, "pageSize": 25 }`.

### `POST /api/v1/workspaces/{workspaceId}/suppliers`
- **Purpose:** Create a supplier master record inside the workspace.
- **Auth:** `WORKSPACE_ADMIN`, `REVIEWER` + CSRF.
- **Request Body:** `{ "name": "...", "gstin": "27AABCA4821M1Z4", "stateCode": "27", "stateName": "Maharashtra", "category": "...", "email": "..." }`
- **Response (`201 Created`):** Supplier DTO (`normalizedName` computed server-side).

### `GET /api/v1/workspaces/{workspaceId}/suppliers/{supplierId}`
- **Purpose:** Retrieve supplier details and invoice aggregates.
- **Auth:** Any active workspace member.
- **Response (`200 OK`):** Supplier summary DTO.

### `PATCH /api/v1/workspaces/{workspaceId}/suppliers/{supplierId}`
- **Purpose:** Update supplier GSTIN, category, contact email, or verification status.
- **Auth:** `WORKSPACE_ADMIN`, `REVIEWER` + CSRF.
- **Response (`200 OK`):** Updated Supplier DTO.

---

## 6. Documents & Invoices Endpoints

### `POST /api/v1/workspaces/{workspaceId}/documents`
- **Purpose:** Upload a PDF/PNG/JPG/WEBP invoice file (`multipart/form-data`), validate magic bytes & size, store in object storage, and optionally create a staged `PENDING_REVIEW` draft invoice.
- **Auth:** `WORKSPACE_ADMIN`, `REVIEWER`, `UPLOADER` + CSRF.
- **Request (`multipart/form-data`):**
  - `file`: binary (max 15 MB)
  - `supplierName`: optional string
  - `invoiceNumber`: optional string
  - `createDraftInvoice`: boolean (default `true`)
- **Response (`201 Created`):** `{ "document": { "id": "uuid", "originalFilename": "...", "mimeType": "...", "byteSize": 102400, "scanStatus": "PENDING" }, "invoiceId": "uuid" }`.
- **Errors:** `413 FILE_TOO_LARGE`, `415 UNSUPPORTED_MEDIA_TYPE`.

### `GET /api/v1/workspaces/{workspaceId}/documents/{documentId}/content`
- **Purpose:** Stream the original document securely to authorized workspace members for side-by-side Review Centre viewing.
- **Auth:** Any active workspace member.
- **Query Params:** `download=true|false` (controls `Content-Disposition`).
- **Response (`200 OK`):** Binary stream with `X-Content-Type-Options: nosniff` and `Cache-Control: private, no-store`.

### `GET /api/v1/workspaces/{workspaceId}/invoices`
- **Purpose:** Search, filter, and sort active (non-soft-deleted) workspace invoices.
- **Auth:** Any active workspace member.
- **Query Params:**
  - `search` (matches invoice number, supplier name, GSTIN)
  - `status` (`PENDING_REVIEW|VERIFIED|FLAGGED`)
  - `taxType` (`INTRA_STATE|INTER_STATE`)
  - `supplierId` (`UUID`)
  - `reconciliationStatus` (`MATCHED|WITHIN_ROUNDING_TOLERANCE|VARIANCE_DETECTED|PENDING_INPUT`)
  - `lineItemReconciliationStatus` (`NO_LINE_ITEMS|MATCHED|VARIANCE_WARNING`)
  - `dateFrom`, `dateTo` (`YYYY-MM-DD`)
  - `sortBy` (`invoiceNumber|supplierName|invoiceDate|totalAmount|taxAmount|status|uploadDate`)
  - `sortDir` (`asc|desc`), `page`, `pageSize`
- **Response (`200 OK`):** `{ "items": [...], "total": 24, "page": 1, "pageSize": 25 }`.

### `POST /api/v1/workspaces/{workspaceId}/invoices`
- **Purpose:** Create a new `PENDING_REVIEW` invoice record manually or linked to an existing uploaded `documentId`. Cannot create an invoice directly in `VERIFIED` state, and **never rejects** an invoice due to line-item vs. header taxable variance (surfaces advisory `lineItemWarning` instead).
- **Auth:** `WORKSPACE_ADMIN`, `REVIEWER`, `UPLOADER` + CSRF.
- **Request Body:** Supplier/buyer snapshots, `invoiceNumber`, `invoiceDate`, `dueDate`, `currency`, `taxableAmount`, `discountAmount`, `discountMode`, `cgstAmount`, `sgstAmount`, `igstAmount`, `cessAmount`, `freightAmount`, `otherChargesAmount`, `roundOffAmount`, `totalAmount`, `lineItems[]`.
- **Response (`201 Created`):** Full `InvoiceDetail` DTO with server-computed `computedExpectedTotal`, `varianceAmount`, `reconciliationStatus`, `lineItemsTaxableSum`, `lineItemVarianceAmount`, `lineItemReconciliationStatus`, `lineItemWarning`, and advisory `duplicateWarning`.

### `GET /api/v1/workspaces/{workspaceId}/invoices/{invoiceId}`
- **Purpose:** Retrieve complete invoice details for the Review Centre: header amounts, buyer/supplier snapshots, `lineItems[]`, `fieldVerifications[]`, open & historical `reviewFlags[]`, header & line-item reconciliation summaries, and document preview descriptor.
- **Auth:** Any active workspace member.
- **Response (`200 OK`):** Complete `InvoiceDetail` DTO.

### `PATCH /api/v1/workspaces/{workspaceId}/invoices/{invoiceId}`
- **Purpose:** Save reviewer edits to invoice fields, line items, reviewer note, or individual field verification statuses. Recalculates `computedExpectedTotal`, `varianceAmount`, advisory `lineItemReconciliationStatus`/`lineItemWarning`, and advisory `duplicateWarning`. Never rejects due to arithmetic or line-item variance; editing a `VERIFIED` invoice requires reopening first (`409` otherwise).
- **Auth:** `WORKSPACE_ADMIN`, `REVIEWER` (or `UPLOADER` while `status == 'PENDING_REVIEW'`) + CSRF.
- **Response (`200 OK`):** Updated `InvoiceDetail` DTO.
- **Errors:** `409 VERIFIED_INVOICE_LOCKED`.

### `DELETE /api/v1/workspaces/{workspaceId}/invoices/{invoiceId}`
- **Purpose:** Soft-delete (`deleted_at`, `deleted_by_user_id`, `deletion_reason`) an unverified `PENDING_REVIEW` or `FLAGGED` invoice while **preserving all `invoice_review_flags`, `review_actions`, and `audit_events` history**. **Never** permits deletion of `VERIFIED` invoices.
- **Auth:** `WORKSPACE_ADMIN` only + CSRF.
- **Request Body (Optional):** `{ "deletionReason": "Duplicate test scan uploaded by mistake" }`
- **Response (`204 No Content`)**
- **Errors:** `403 FORBIDDEN_ROLE`, `409 CANNOT_DELETE_VERIFIED_INVOICE`.

---

## 7. Invoice Review & Flag Endpoints

### `POST /api/v1/workspaces/{workspaceId}/invoices/{invoiceId}/verify`
- **Purpose:** Human sign-off transitioning an invoice to `VERIFIED`. Records an immutable `review_actions` entry and resolves compatible open flags if requested.
- **Auth:** `WORKSPACE_ADMIN`, `REVIEWER` only (`UPLOADER` and `VIEWER` forbidden) + CSRF.
- **Request Body:**
  ```json
  {
    "confirmVarianceAcknowledgment": true,
    "confirmationNote": "Confirmed ₹1,000.00 un-itemized pallet surcharge on scanned copy.",
    "resolveOpenFlags": true
  }
  ```
- **Response (`200 OK`):** Updated `InvoiceDetail` DTO (`status: "VERIFIED"`, `verifiedBy`, `verifiedAt`).
- **Errors:**
  - `409 VARIANCE_ACKNOWLEDGMENT_REQUIRED` (returned whenever header `abs(varianceAmount) > roundingTolerance` **or** `lineItemReconciliationStatus == "VARIANCE_WARNING"` and `confirmVarianceAcknowledgment` is false or `confirmationNote` is blank).
  - `422 INVALID_FLAG_RESOLUTION`.

### `POST /api/v1/workspaces/{workspaceId}/invoices/{invoiceId}/flag`
- **Purpose:** Hold an invoice (`status = 'FLAGGED'`) and create an `invoice_review_flags` row plus `review_actions` entry.
- **Auth:** `WORKSPACE_ADMIN`, `REVIEWER` + CSRF.
- **Request Body:**
  ```json
  {
    "flagCategory": "ARITHMETIC_MISMATCH",
    "reasonText": "Tax / total arithmetic mismatch — Freight omitted from GST base"
  }
  ```
- **Response (`200 OK`):** Updated `InvoiceDetail` DTO with new `invoice_review_flags` record.
- **Errors:** `422 EMPTY_FLAG_REASON` (rejects empty/whitespace `reasonText`).

### `POST /api/v1/workspaces/{workspaceId}/invoices/{invoiceId}/flags/{flagId}/resolve`
- **Purpose:** Mark an open review flag as `RESOLVED` or `DISMISSED` with a mandatory resolution note; optionally transitions invoice back to `PENDING_REVIEW` if no open flags remain.
- **Auth:** `WORKSPACE_ADMIN`, `REVIEWER` + CSRF.
- **Request Body:** `{ "resolutionStatus": "RESOLVED", "resolutionNote": "...", "reopenToPending": true }`
- **Response (`200 OK`):** Updated flag + invoice status summary.

### `POST /api/v1/workspaces/{workspaceId}/invoices/{invoiceId}/reopen`
- **Purpose:** Reopen a `VERIFIED` or `FLAGGED` invoice to `PENDING_REVIEW` for re-editing, logging an immutable `review_actions` row.
- **Auth:** `WORKSPACE_ADMIN`, `REVIEWER` + CSRF.
- **Request Body:** `{ "reason": "Supplier issued credit note / revised GSTIN" }`
- **Response (`200 OK`):** Updated `InvoiceDetail` DTO.

### `GET /api/v1/workspaces/{workspaceId}/invoices/{invoiceId}/review-history`
- **Purpose:** Return chronological `review_actions` and `invoice_review_flags` for a specific invoice (remains readable for audit purposes).
- **Auth:** Any active workspace member.
- **Response (`200 OK`):** `{ "actions": [...], "flags": [...] }`.

---

## 8. Reports & Exports Endpoints

### `GET /api/v1/workspaces/{workspaceId}/reports/summary`
- **Purpose:** Compute live workspace KPIs and tax totals across active (non-soft-deleted) invoices (`totalInvoices`, status counts/values, `verificationRatePercent`, `totalTaxableValue`, `totalCgst`, `totalSgst`, `totalIgst`, `totalCess`, `totalGst`, `totalInvoiceValue`).
- **Auth:** Any active workspace member.
- **Query Params:** Optional `dateFrom`, `dateTo`.
- **Response (`200 OK`):** Summary metrics DTO.

### `GET /api/v1/workspaces/{workspaceId}/reports/monthly-trend`
- **Purpose:** Return chronological zero-filled monthly invoice counts and values derived dynamically from valid `invoiceDate` values.
- **Auth:** Any active workspace member.
- **Query Params:** `window=6m|12m|all` (default `6m`).
- **Response (`200 OK`):** `{ "window": "6m", "buckets": [{ "monthKey": "2026-11", "label": "Nov 26", "totalCount": 3, "verifiedCount": 2, "pendingCount": 1, "flaggedCount": 0, "totalValue": "345000.00" }], "excludedCount": 0 }`.

### `GET /api/v1/workspaces/{workspaceId}/reports/exceptions`
- **Purpose:** List `FLAGGED` invoices and unresolved `VARIANCE_DETECTED` / `VARIANCE_WARNING` records for exception reporting.
- **Auth:** Any active workspace member.
- **Response (`200 OK`):** `{ "items": [...] }`.

### `GET /api/v1/workspaces/{workspaceId}/reports/export.csv`
- **Purpose:** Generate RFC-4180 CSV register export with server-side formula-injection neutralization (`'=` prefixing) and record an `audit_events` log entry.
- **Auth:** `WORKSPACE_ADMIN`, `REVIEWER`, `VIEWER`.
- **Query Params:** Optional `status`, `dateFrom`, `dateTo`.
- **Response (`200 OK`):** `text/csv; charset=utf-8` with `Content-Disposition: attachment; filename="norus-billwise-report-YYYY-MM-DD.csv"`.

---

## 9. Audit History Endpoints

### `GET /api/v1/workspaces/{workspaceId}/audit-events`
- **Purpose:** Retrieve chronological append-only workspace activity and compliance events (including soft-delete and auth/security events).
- **Auth:** `WORKSPACE_ADMIN`, `REVIEWER`, `VIEWER` (`UPLOADER` restricted to `actorUserId == currentUser.id`).
- **Query Params:** `entityType`, `entityId`, `eventType`, `actorUserId`, `dateFrom`, `dateTo`, `page`, `pageSize`.
- **Response (`200 OK`):**
  ```json
  {
    "items": [
      {
        "id": "uuid",
        "eventType": "invoice.verified",
        "entityType": "invoice",
        "entityId": "uuid",
        "actorDisplayName": "CA Ananya Deshmukh",
        "summary": "Marked invoice as Verified after human confirmation of 1,000.00 variance",
        "tone": "success",
        "createdAt": "2026-11-16T10:30:00Z"
      }
    ],
    "total": 42,
    "page": 1,
    "pageSize": 25
  }
  ```
