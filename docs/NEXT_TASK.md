# NEXT_TASK — Exact Next Recommended Development Task

## Task 002: Backend Foundation (Python FastAPI + PostgreSQL + Workspace API)

Do not begin Task 002 until Task 001 has been reviewed and approved.

### Scope for Task 002

1. **Initialize Backend Service (`/backend`)**
   - Set up Python FastAPI application structure with Pydantic v2 schemas matching `src/types/domain.ts`.
   - Configure PostgreSQL connection, SQLAlchemy 2.0 models, and Alembic migrations.
2. **Core Database Schema**
   - `workspaces`, `users`, `suppliers`, `invoices`, `invoice_line_items`, `invoice_field_evidence`, and `audit_events`.
   - Enforce `workspace_id` multi-tenant scoping on all queries.
3. **REST API Endpoints**
   - `GET /api/v1/invoices`, `GET /api/v1/invoices/{id}`, `PATCH /api/v1/invoices/{id}`
   - `POST /api/v1/invoices/upload` (store original PDF/image in local dev object storage or S3-compatible bucket and stage as `Pending Review`)
   - `POST /api/v1/invoices/{id}/verify` and `POST /api/v1/invoices/{id}/flag`
   - `GET /api/v1/suppliers`, `GET /api/v1/reports/summary`, `GET /api/v1/reports/export.csv`
4. **Frontend API Client Adapter**
   - Replace `src/data/mockData.ts` / `localStorage` calls inside `WorkspaceContext` with typed API client calls while preserving the exact UI and human-review workflow.
5. **Automated Backend Tests**
   - Add `pytest` unit and integration tests for GST arithmetic validation, duplicate warning detection, and status transition audit logging.
