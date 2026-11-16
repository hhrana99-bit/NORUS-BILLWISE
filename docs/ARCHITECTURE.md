# ARCHITECTURE — NORUS BILLWISE

## 1. Task 001 Frontend Architecture

The Task 001 prototype follows a clean 4-layer client architecture designed to swap local mock state for Python FastAPI REST endpoints cleanly in subsequent tasks:

1. **Domain Layer (`src/types/domain.ts`)**: Strongly typed interfaces for `Invoice`, `InvoiceLineItem`, `InvoiceFieldMeta`, `Supplier`, `WorkspaceSettings`, and `ActivityEvent`.
2. **Services Layer (`src/services/`)**: Pure TypeScript modules with zero React dependencies:
   - `formatters.ts`: INR currency (`en-IN`), compact Lakhs/Crores display, `DD/MM/YYYY` formatting.
   - `invoiceService.ts`: Filtering, multi-column sorting, live arithmetic check (`Taxable + CGST + SGST + IGST` vs `Total`), supplier aggregation, and local demo file staging.
   - `reportService.ts`: KPI/GST totals, monthly trend series builder, and RFC-4180 compliant CSV export.
   - `storageService.ts`: Safe `localStorage` persistence (automatically stripping session-scoped `ObjectURL` references on serialize/deserialize).
3. **State Layer (`src/state/WorkspaceContext.tsx`)**: Centralized reactive store coordinating all 6 views, notification read states, audit activity log, and workspace settings.
4. **Presentation Layer (`src/components/` & `src/pages/`)**: Reusable UI primitives (`Card`, `KpiCard`, `StatusBadge`, `EmptyState`), responsive navigation shell (`Sidebar`, `TopBar`, `AppShell`), and 6 functional screens.

## 2. Planned Full-Stack Target Architecture (Task 002+)

- **API Server:** Python FastAPI with Pydantic schemas mirroring `src/types/domain.ts`.
- **Database:** PostgreSQL with multi-tenant `workspace_id` isolation, immutable audit log tables, and supplier master tables.
- **Document & Extraction Pipeline:** Object storage for original PDFs/images -> OCR service -> AI field suggestion service -> Verification & duplicate warning engine -> Human Review Centre.
- **Auth & RBAC:** JWT/session authentication with Firm Partner, Reviewer, and Client Read-Only roles.
