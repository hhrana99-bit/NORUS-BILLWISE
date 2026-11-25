# NEXT_TASK — Exact Next Recommended Development Task

## Baseline & Checkpoint (`7d4783dcd2824b4dda81815a91674a583f812ba0` + Task 002.7)

Remote `main` (`7d4783dcd2824b4dda81815a91674a583f812ba0`) passed GitHub Actions CI run #26 (`45016892293`) completely across Frontend (Node 22) and Backend (Python 3.12 + PostgreSQL 16). Task 002.7 implements the Reports & Formula-Safe CSV Export API (`/reports/summary`, `/monthly-trend`, `/exceptions`, `/export.csv`), `/audit-events` validation/tie-break fixes, and full React SPA API client + `WorkspaceContext` integration, along with `backend/tests/test_reports_and_audit.py` and `tests/apiClient.test.ts`. Apply `NORUS-TASK-002-7.patch` on a dedicated feature branch and verify full green GitHub Actions CI (`pytest -v -ra` against PostgreSQL 16 + Node 22 frontend suite) plus live full-stack browser QA before merging and starting Task 002.8.

---

## Immediate Next Implementation Batch: NORUS BILLWISE TASK 002.8 — Document Malware Scanning Pipeline, Object Storage & Controlled Pilot Readiness

### Objective
Enable end-to-end controlled accounting-firm pilot testing by moving uploaded invoice binaries through a real malware-scanning lifecycle (`PENDING -> CLEAN | INFECTED | FAILED`) so verified `CLEAN` PDFs/images stream safely in Review Centre, adding production object storage support, and hardening deployment/rate-limit controls.

### Deliverables

1. **Malware Scanning Pipeline (`ClamAV` / Scanner Port)**
   - Implement a `DocumentScanner` service port with ClamAV (`clamd`) adapter and explicit quarantine/failure transitions (`PENDING -> CLEAN | INFECTED | FAILED`), preserving `CLEAN`-only gating on `/documents/{documentId}/content` and emitting `document.scanned` audit events.
   - Add per-user/workspace upload and content-stream rate limits.
2. **Production Object Storage (`S3` / `MinIO` Adapter) & Cleanup**
   - Implement an `S3DocumentStorage` adapter alongside `LocalFilesystemStorage` behind `DocumentStorage` with SSE encryption options and orphan-blob lifecycle cleanup.
3. **Controlled Pilot Deployment & Live Full-Stack E2E Verification**
   - Provide pilot HTTPS / reverse-proxy Docker Compose configuration (`COOKIE_SECURE=true`, `CORS_ORIGINS`, `TRUSTED_PROXIES`, persistent volumes), verify `SELECT`/`INSERT`-only DBA role guidance on append-only audit tables, and run end-to-end Playwright Chromium verification against live FastAPI + PostgreSQL 16 across all 6 UI routes.

---

## Subsequent Releases (Toward General Availability & Post-MVP)

- **Auth & Compliance Polish:** Email verification (`users.email_verified_at`), password-reset token lifecycle, workspace storage quotas, automated PostgreSQL PITR restore drills, and structured metrics/alerting.
- **Task 003+ (OCR & AI Extraction):** Asynchronous OCR/AI extraction workers proposing invoice field candidates and bounding-box source evidence while keeping human verification (`requireHumanReview = true`) strictly mandatory.
