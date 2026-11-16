# NEXT_TASK — Exact Next Recommended Development Task

## Immediate Pre-Task Release Sync

1. Push the verified frontend changes and `.github/workflows/ci.yml` to branch `task-001-2-remediation` (confirming `bun.lock` is not committed).
2. Verify the GitHub Actions **Frontend CI** workflow (`npm ci`, `npm run lint`, `npm test`, `npm run build`) passes on `task-001-2-remediation` and open/merge the PR to `main`.

---

## Next Development Milestone: Task 002 — Backend Foundation (Python FastAPI + PostgreSQL)

1. **Initialize Backend Service (`/backend`)**
   - Set up Python FastAPI application structure with Pydantic v2 schemas matching `src/types/domain.ts`.
   - Configure PostgreSQL connection, SQLAlchemy 2.0 models, and Alembic migrations.
2. **Core Database Schema**
   - `workspaces`, `users`, `suppliers`, `invoices`, `invoice_line_items`, `invoice_field_evidence`, and `audit_events`.
   - Enforce `workspace_id` multi-tenant scoping on all queries.
3. **REST API Endpoints**
   - `GET /api/v1/invoices`, `GET /api/v1/invoices/{id}`, `PATCH /api/v1/invoices/{id}`
   - `POST /api/v1/invoices/upload`, `POST /api/v1/invoices/{id}/verify`, `POST /api/v1/invoices/{id}/flag`
   - `DELETE /api/v1/invoices/{id}` (staging drafts), `GET /api/v1/suppliers`, `GET /api/v1/reports/summary`, `GET /api/v1/reports/export.csv`
4. **Frontend API Client Adapter**
   - Add async loading/error states and API adapter calls inside `WorkspaceContext` while preserving the mandatory human-review gate and verification mismatch safety checks.


