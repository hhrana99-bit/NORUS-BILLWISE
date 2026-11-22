# NEXT_TASK — Exact Next Recommended Development Task

## Verified Baseline (`b3e0460959e996260a51f3c0e35673ee943640a4` — CI #22 Green)

Remote `main` (`b3e0460959e996260a51f3c0e35673ee943640a4`) is **100% green** on GitHub Actions CI #22 (`45010488214`) for both `Frontend Lint, Test & Build (Node 22)` and `Backend Compilation, Pytest & PostgreSQL 16 Migrations`.

*(Note: Apply the Task 002.4H cleanup PR removing `NORUS-TASK-002-4D.patch` and updating `docs/`, or start Task 002.5 directly on top of clean `main`.)*

---

## Immediate Next Implementation Batch: NORUS BILLWISE TASK 002.5 — Invoices CRUD, Flexible Indian GST & Line-Item Reconciliation Engine, and Advisory Duplicate Detection

### Objective
Implement the core invoice lifecycle APIs on top of Task 002.4A (`suppliers`) and Task 002.4B/C (`documents`), delivering flexible GST & line-item reconciliation, advisory duplicate detection, strict RBAC/CSRF/tenant isolation, and mandatory human-review gating (never auto-verifying invoices).

### Deliverables

1. **Invoice Schemas & Decimal Calculators (`backend/app/schemas/invoices.py`, `backend/app/services/reconciliation_service.py`)**
   - Support list filtering/sorting/pagination (`GET /api/v1/workspaces/{workspaceId}/invoices`), manual/document-linked creation (`POST`, always initializing in `PENDING_REVIEW` and never `VERIFIED`), detail retrieval (`GET /{invoiceId}`), and partial updates (`PATCH /{invoiceId}`, locked against editing `VERIFIED` invoices unless reopened).
   - Compute `computedExpectedTotal`, `varianceAmount`, `reconciliationStatus`, `lineItemsTaxableSum`, `lineItemVarianceAmount`, `lineItemReconciliationStatus`, and advisory `lineItemWarning` strictly with fixed-point `Decimal` math without ever rejecting an invoice upload/save for arithmetic variance.
   - Verify any linked `supplierId` or `documentId` belongs to the exact same `workspaceId` (`404` on foreign references) and populate buyer/supplier snapshots safely.
2. **Advisory Duplicate Warning Engine (`backend/app/services/invoice_service.py`)**
   - Detect workspace-scoped active (`deleted_at IS NULL`) invoices sharing `(supplier_id, normalized_invoice_number)` or `(supplier_id, total_amount ± 0.01, invoice_date ± 45 days)` (respecting `WorkspaceSettings.enable_duplicate_warnings`) and surface advisory `duplicateWarning` for human review rather than silent rejection.
3. **PostgreSQL 16 Integration Tests (`backend/tests/test_invoices.py`)**
   - Cover GST intra/inter-state & `PRE_TAX`/`POST_TAX_COMMERCIAL` discount arithmetic, cess/freight/round-off handling, rounding tolerance, line-item variance advisories, duplicate warnings, `UPLOADER` edit restriction to `PENDING_REVIEW` only, `VERIFIED` lock (`409 VERIFIED_INVOICE_LOCKED`), soft-deleted invoice exclusion, CSRF, cross-tenant `supplierId`/`documentId` `404` isolation, and N+1 query bounds.

---

## Subsequent Dependency-Ordered Batches Toward Pilot & Production

- **Task 002.6 (Human Review Workflow):** Implement `/verify`, `/flag`, `/flags/{flagId}/resolve`, `/reopen`, `/review-history`, `WORKSPACE_ADMIN` soft-delete (`PENDING_REVIEW` / `FLAGGED` only; `409` on `VERIFIED`), mandatory variance confirmation (`confirmVarianceAcknowledgment`), immutable `review_actions` ledger, and `audit_events` emission.
- **Task 002.7 (Reporting, CSV Export & Frontend API Integration):** Implement `/reports/summary`, `/monthly-trend`, `/exceptions`, formula-safe `/export.csv`, wire React `WorkspaceContext` to FastAPI (`credentials: 'include'` + `X-CSRF-Token`, sign-in/workspace switcher UI, removing mock-only dependency), and run full-stack Playwright + FastAPI verification.
- **Pilot Security & Document Scan Readiness (Task 002.8):** Integrate ClamAV/malware scanning worker + scan-status transition flow (`PENDING -> CLEAN | INFECTED | FAILED`) so uploaded PDFs/images can safely stream in Review Centre, add upload/download rate limits, configure S3/MinIO `DocumentStorage` adapter + pilot HTTPS deployment hardening, and add email verification / password reset before onboarding external firms.
