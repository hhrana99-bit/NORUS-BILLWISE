# STATUS — Project Progress

**Current Milestone:** Task 002.1A — Architecture Decision Finalization  
**Status:** Complete (All Core Backend Decisions Finalized — Ready for Task 002.2 Implementation)

## Completed Work in Task 002.1 & 002.1A

1. **System & Multi-Tenant Architecture (`docs/BACKEND_ARCHITECTURE.md`)**
   - Designed the Python FastAPI + PostgreSQL 16+ + SQLAlchemy 2.0 + Alembic layered modular monolith and portable object storage abstraction (`DocumentStorage`).
   - Defined strict `Organization -> Workspace -> WorkspaceMembership` tenancy isolation and RBAC (`WORKSPACE_ADMIN`, `REVIEWER`, `UPLOADER`, `VIEWER`).
   - Finalized all four core architectural decisions in Task 002.1A:
     1. **API JSON Naming:** `camelCase` JSON requests/responses matching `src/types/domain.ts`, while keeping Python variables and PostgreSQL columns `snake_case`.
     2. **Authentication & Security:** Secure `HttpOnly`, `Secure`, `SameSite=Lax` cookie sessions (`norus_access_token` + path-scoped `norus_refresh_token`), double-submit CSRF protection (`norus_csrf_token` + `X-CSRF-Token`), refresh rotation with token-family reuse revocation, `/auth/logout` & `/auth/logout-all`, and zero auth tokens in `localStorage`.
     3. **Invoice Line-Item Reconciliation:** Header taxable amount vs. line-item totals variance produces an advisory `VARIANCE_WARNING`, never auto-rejects, and requires human review/confirmation (`confirmVarianceAcknowledgment`).
     4. **Draft Deletion Policy:** Authorized `WORKSPACE_ADMIN` users only may soft-delete unverified `PENDING_REVIEW` and `FLAGGED` invoices while preserving audit/flag/review history; `VERIFIED` invoices can never be deleted via this operation.
2. **PostgreSQL Database Schema (`docs/DATABASE_SCHEMA.md`)**
   - Specified UUID-keyed `snake_case` tables (`organizations`, `users`, `user_sessions`, `workspaces`, `workspace_settings`, `organization_memberships`, `workspace_memberships`, `suppliers`, `documents`, `invoices`, `invoice_line_items`, `invoice_field_verifications`, `invoice_review_flags`, `review_actions`, `audit_events`) including session rotation chains, line-item variance fields, and `CHECK ((deleted_at IS NULL) OR (status IN ('PENDING_REVIEW', 'FLAGGED')))`.
3. **REST API Contract (`docs/API_CONTRACT.md`)**
   - Standardized `/api/v1` endpoints, `camelCase` DTOs/query params, cookie/CSRF lifecycle (`/auth/logout`, `/auth/logout-all`), advisory reconciliation responses, and `WORKSPACE_ADMIN` draft deletion rules.
4. **Phased Implementation Roadmap (`docs/BACKEND_ARCHITECTURE.md`, `docs/NEXT_TASK.md`)**
   - Decomposed backend implementation into testable milestones (`Task 002.2` through `Task 002.7`).

---

## Completed Work in Task 001.3 (Frontend Foundation & Browser QA)

1. **Real Chromium Browser QA (`375px`, `768px`, `1280px` × all 6 routes)**
   - Verified zero page-level horizontal overflow (`scrollWidth === innerWidth`), zero unlabelled visible icon buttons, zero console errors, zero uncaught page errors, and zero failed internal asset requests across all 18 viewport/route states (`vite preview`).
   - Verified all interactive user flows end-to-end (upload staging, search/filter/sort/supplier drill-down, local-only delete restriction, 3-choice unsaved-edits guard, custom flag validation, mismatch confirmation gate, PDF zoom/reset, `URL.revokeObjectURL`, dynamic `6M`/`All` charts, CSV formula sanitization, Settings persistence, corrupted `localStorage` recovery, and mobile keyboard/`Escape` handling).
2. **Release Audit Defect Fix (`src/pages/ReviewCentrePage.tsx`)**
   - Fixed `useEffect([currentInvoice])` clearing `feedbackBanner` after Save/Flag/Verify/Delete actions and removed the 1-frame stale `draft.id` lag during guarded switches.
3. **GitHub Actions CI (`.github/workflows/ci.yml`) & Automated Checks**
   - Verified `npm ci`, `npm run lint` (`tsc --noEmit`), `npm test` (`11/11` service tests), and `npm run build` (`vite build` route-split chunks).

## Implemented vs. Proposed Breakdown

- **Implemented & Verified (Frontend Prototype):** React 19 + TypeScript SPA with fictional Indian GST sample data, `localStorage` persistence (`v2`), client-side CSV export, and browser-local file staging (`npm run lint`, `npm test`, `npm run build`, and Playwright Chromium QA verified in Task 001.3).
- **Proposed Design Only (Not Yet Implemented):** Python FastAPI backend, PostgreSQL database, Alembic migrations, Argon2id/JWT auth, RBAC memberships, server-side file storage, and Task 003+ OCR/AI extraction workers.

## Remaining Non-Blocking Limitations

- `beforeunload` browser confirmation prompt is wired in React (`ReviewCentrePage.tsx`) and statically verified, but was not triggered via a full native browser unload dialog test.
- Legacy unused exports `HISTORICAL_MONTH_BASELINES` (`src/data/mockData.ts`) and `updateInvoiceStatus` (`src/state/WorkspaceContext.tsx`) remain unused by UI components.
- `.git` is unavailable inside the AI Studio container runtime, so repository sync to GitHub branch `task-001-2-remediation` (and triggering `.github/workflows/ci.yml`) must be executed from the connected GitHub export/local clone.


