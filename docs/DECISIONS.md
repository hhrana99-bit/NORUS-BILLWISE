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
