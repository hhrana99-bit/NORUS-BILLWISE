# DECISIONS — Architectural & Product Decision Log

## ADR-001: Decoupled Services Layer in Task 001
- **Decision:** Place filtering, sorting, GST arithmetic verification, supplier summary aggregation, and CSV export in pure TypeScript modules under `src/services/`.
- **Rationale:** Keeps business logic testable and portable across future API-backed hooks without rewriting React components.

## ADR-002: Zero External Chart or State Libraries in Prototype
- **Decision:** Implement monthly stacked bar charts and status progress visualizations using semantic HTML + Tailwind CSS rather than adding heavy third-party chart bundles, and use React Context for workspace state.
- **Rationale:** Minimizes dependency surface area, ensures instant bundle builds, and keeps styling 100% consistent with the design system.

## ADR-003: Session-Safe Local File Staging
- **Decision:** Allow PDF/image preview via `URL.createObjectURL` in the `UploadInvoiceModal` while explicitly stripping ephemeral `blob:` URLs from `localStorage` persistence and displaying clear prototype notices.
- **Rationale:** Prevents broken blob URL errors after browser reload while supporting immediate interactive document preview during a session.

## ADR-004: Mandatory Human Review Enforcement in Settings
- **Decision:** Keep `requireHumanReview` locked (`true`) in `WorkspaceSettings` and visibly communicated in both the Sidebar and Settings page.
- **Rationale:** Reflects NORUS BILLWISE core principle #1: AI suggestions never automatically become approved accounting records.

## ADR-005: Advisory-Only Duplicate Warnings
- **Decision:** Surface potential duplicate invoices (e.g., `VCS-2026-884`) as amber advisory banners in the Review Centre rather than blocking or rejecting records.
- **Rationale:** Recurring monthly retainers with identical amounts are common in accounting practices and require CA confirmation, not silent rejection.

## ADR-006: WorkspaceContext-Mediated Unsaved Review Guard
- **Decision:** Track `hasUnsavedReviewChanges` and `pendingNavigation` inside `WorkspaceContext` while coordinating `ReviewCentrePage` commit/discard handlers and `beforeunload`.
- **Rationale:** Protects both internal invoice switcher transitions and top-bar/sidebar route navigation without coupling layout components directly to form draft state.

## ADR-007: Verification Arithmetic Safety Gate
- **Decision:** Prevent silent verification when `computeArithmeticCheck` detects a discrepancy (`Taxable + CGST + SGST + IGST !== Total`), requiring an explicit confirmation dialog while preserving exact figures.
- **Rationale:** Prevents accidental approval of out-of-balance GST bills without silently mutating accounting numbers.

## ADR-008: Dynamic Chronological Monthly Reporting Windows
- **Decision:** Remove hardcoded baseline month buckets and generate monthly trend series dynamically from valid `YYYY-MM-DD` invoice dates across `6M`, `12M`, or `All` windows, zero-filling empty intermediate months.
- **Rationale:** Keeps Reports accurate as new demo/staged invoices across arbitrary dates are added or deleted.

## ADR-009: Reference-Tracked Object URL Lifecycle Cleanup
- **Decision:** Manage `blob:` URL revocation via `src/services/objectUrlService.ts` and a `createdBlobUrlsRef` set in `WorkspaceContext` across deletion, update replacement, workspace reset, and provider unmount.
- **Rationale:** Eliminates browser memory leaks while staying safe under React 19 StrictMode mount/unmount checks.

## ADR-010: Route-Level Code Splitting with React.lazy
- **Decision:** Split the 6 primary pages via `React.lazy` and `Suspense` in `src/App.tsx` and use `fileURLToPath(import.meta.url)` in `vite.config.ts`.
- **Rationale:** Eliminates Vite 8 ESM `__dirname` warnings and keeps the initial entry chunk lightweight.

## ADR-011: Same-Invoice Effect Isolation & Automated CI Gate
- **Decision:** Scope `ReviewCentrePage` banner/modal reset exclusively to `currentInvoice.id` transitions (`prevInvoiceIdRef`), derive active draft synchronously across invoice switches, and enforce `npm ci`, `npm run lint`, `npm test`, and `npm run build` in `.github/workflows/ci.yml`.
- **Rationale:** Prevents `updateInvoice` state refreshes from erasing human action feedback banners while guaranteeing repeatable frontend build/test verification on `main` and `task-001-2-remediation`.


