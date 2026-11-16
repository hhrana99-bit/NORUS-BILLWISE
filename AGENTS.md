# AGENTS.md — Engineering & Architecture Guide for NORUS BILLWISE

## 1. Product Vision

- **Company:** NORUS AI
- **Product:** NORUS BILLWISE (*Beyond the World.*)
- **Mission:** Help Chartered Accountants, accounting firms, bookkeepers, and business finance teams transform supplier invoices into structured, reviewable accounting records through intelligent document processing, verification, and mandatory human review.
- **Target Markets:** Initial launch focused on India (INR, GSTIN, CGST/SGST/IGST, HSN/SAC); architecture designed to expand globally.

## 2. Technology Choices

- **Frontend (Task 001):** React + TypeScript + Vite + Tailwind CSS v4 + Lucide React.
- **Planned Backend (Task 002+):** Python FastAPI + PostgreSQL + SQLAlchemy/Alembic + object storage + OCR & AI extraction workers.
- **Dependency Hygiene:** Keep dependencies minimal and portable. Do not tie core domain models or business rules to proprietary SaaS SDKs.

## 3. Coding Conventions

- Strict TypeScript (`noEmit`, clean modular interfaces in `src/types/domain.ts`).
- Business logic (filtering, sorting, arithmetic reconciliation, CSV generation, report aggregation) lives in `src/services/`, completely decoupled from React UI components.
- State management in `src/state/WorkspaceContext.tsx` can later be backed by API calls without rewriting page layouts.
- Financial figures must always use tabular numerals (`font-mono tabular-nums`) and `Intl.NumberFormat('en-IN')` currency formatting.

## 4. Security & Product Principles

1. **Human Review Gate:** AI suggestions must never automatically become approved accounting records. Human sign-off is mandatory.
2. **Source Evidence:** Extracted values must eventually link to bounding-box/page source evidence in the original document.
3. **Advisory Duplicate Warnings:** Duplicate detection must produce warnings for human review, never silent auto-rejection.
4. **Data Protection:** Customer financial information must be protected. Never hardcode secret API keys or commit real customer invoices.
5. **Honest Claims:** Never claim untested extraction accuracy or pretend backend processing exists before it is built.

## 5. Project Structure

```text
├── README.md
├── AGENTS.md
├── docs/
│   ├── PRODUCT_SPEC.md
│   ├── ARCHITECTURE.md
│   ├── DECISIONS.md
│   ├── STATUS.md
│   ├── NEXT_TASK.md
│   └── TESTING.md
└── src/
    ├── types/domain.ts
    ├── data/mockData.ts
    ├── services/
    │   ├── formatters.ts
    │   ├── invoiceService.ts
    │   ├── reportService.ts
    │   └── storageService.ts
    ├── state/WorkspaceContext.tsx
    ├── components/
    │   ├── common/
    │   ├── layout/
    │   └── invoices/
    └── pages/
```

## 6. AI & Developer Portability Requirements

- GitHub remains the permanent source of truth.
- Every task must leave the repository buildable (`npm run lint && npm run build`) and update `docs/STATUS.md` and `docs/NEXT_TASK.md`.
- Keep frontend components independent of any specific hosting environment so the codebase runs identically in local Vite dev, CI, or Dockerized builds.
