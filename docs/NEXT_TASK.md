# NEXT_TASK — Exact Next Recommended Development Task

## Baseline & Checkpoint (`4a6a9c063df9182d2d2509b77c4781e591a04d1d` + Task 002.8.2 Hardening)

Remote `main` (`4a6a9c063df9182d2d2509b77c4781e591a04d1d`) includes Task 002.7 (`2fdde31f`) and Task 002.8 (`4a6a9c06`). Local workspace changes complete Task 002.8.2 (`vite.config.ts` `loadEnv` production Demo Mode warning check + expanded 25-test regression suite + doc alignment).

**Immediate CI Stabilization Prerequisite:** GitHub Actions CI #27 (`45584229786`, `2fdde31f`) and CI #28 (`45586606505`, `4a6a9c06`) passed Node 22 frontend checks and Alembic PostgreSQL 16 migrations, but **FAILED** step 9 (`pytest -v -ra`). Inspect CI logs directly and verify the root cause (including `backend/tests/test_reports_and_audit.py:487,519` where `InvoiceCreateRequest` `_clean_optional_note` strips leading whitespace from `reviewerNote` prior to CSV export) on a dedicated feature branch until CI is completely green (`Frontend` + `Backend pytest`), and run live browser QA with both `VITE_DEMO_MODE="false"` and `VITE_DEMO_MODE="true"` before merging. Remove or retire temporary Demo Mode before controlled customer pilot release.

---

## Immediate Next Implementation Batch: NORUS BILLWISE TASK 002.9 — Document Malware Scanning Pipeline, Object Storage & Controlled Pilot Readiness

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
