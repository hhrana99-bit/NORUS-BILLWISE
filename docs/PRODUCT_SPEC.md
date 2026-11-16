# PRODUCT SPEC — NORUS BILLWISE

## 1. Identity & Positioning

- **Company:** NORUS AI
- **Product:** NORUS BILLWISE
- **Tagline:** Beyond the World.
- **Primary Users:** Chartered Accountants, accounting firms, bookkeeping professionals, business finance teams.
- **Initial Market:** India GST accounting workflows (CGST, SGST, IGST, GSTIN, HSN/SAC, INR).

## 2. Core Workflow

1. **Ingest:** Supplier PDFs or images enter a workspace queue (`Pending Review`).
2. **Structure & Suggest (Planned Backend):** OCR + AI extraction will propose supplier, invoice metadata, line items, and tax breakup alongside bounding-box source evidence.
3. **Human Review (Core UI):** Reviewers inspect the original document side-by-side against structured fields, verify arithmetic reconciliation, resolve duplicate/GSTIN warnings, and explicitly `Mark as Verified` or `Flag for Review`.
4. **Report & Export:** Verified registers produce GST summaries, exception reports, and clean CSV/Excel exports.

## 3. Non-Negotiable Product Guardrails

- No auto-posting of AI-extracted values to approved accounting records without human confirmation.
- Duplicate detection surfaces warnings, never silent automatic rejections.
- No fabricated accuracy claims in UI or marketing copy.
- No real client financial data stored in frontend demo fixtures.
