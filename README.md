# NORUS BILLWISE

**Company:** NORUS AI  
**Product:** NORUS BILLWISE  
**Tagline:** *Beyond the World.*  
**Stage:** Task 001.3 — Final Frontend Release Audit & Browser QA (Ready for Task 002)

NORUS BILLWISE is an AI-powered Invoice Intelligence and Verification Workspace built for Chartered Accountants, accounting firms, bookkeeping professionals, and business finance teams (initial target market: India; future target market: global).

## What Task 001 + 001.2A–001.3 Include

- Full B2B SaaS application shell with route-level `React.lazy` code splitting, mobile global search toggle, keyboard-accessible modals/drawers, and responsive sidebar/top navigation
- **Dashboard:** Real-time KPI cards, GST processing overview, status breakdown, pending review queue, activity log, and supplier summary
- **Invoices:** Searchable, filterable (including normalized supplier drill-down for locally staged files), sortable invoice register, local browser demo PDF/image staging modal, and confirmed deletion for locally staged drafts (`isLocalUpload`)
- **Review Centre:** Split-screen document preview (dynamic Workspace buyer details + scalable PDF/simulated zoom) alongside editable GST fields (`Taxable`, `CGST`, `SGST`, `IGST`, `Total`), unsaved changes guard (in-app 3-choice modal + `beforeunload`), custom flag reason modal, verification arithmetic mismatch safety gate, advisory duplicate detection, per-field verification statuses, persistent status feedback banners, and Object URL lifecycle cleanup
- **Suppliers:** Fictional Indian GSTIN vendor directory with aggregated invoice totals and invoice drill-down
- **Reports:** Verification metrics, dynamic chronological Monthly Volume Trend (`6M` / `12M` / `All` windows computed directly from valid invoice dates), flagged exception report, and formula-injection-safe CSV export
- **Settings:** Workspace, company, verification, regional, notification, and privacy preferences persisted locally in schema-versioned `localStorage`
- **CI:** `.github/workflows/ci.yml` runs `npm ci`, `npm run lint`, `npm test`, and `npm run build` on pushes and PRs targeting `main` and `task-001-2-remediation`

## Tech Stack

- React 19 + TypeScript (strict mode enabled)
- Vite 8 + Tailwind CSS v4 (`@tailwindcss/vite`)
- Lucide React icons
- `npm` package manager (`package-lock.json`)

## Local Development

```bash
npm ci
npm run dev
```

To typecheck, run unit tests, and build for production:

```bash
npm run lint
npm test
npm run build
```

## Important Prototype Caveats

- Uses fictional Indian GST sample data only.
- No backend server, PostgreSQL database, OCR engine, or AI extraction is connected yet.
- Uploaded files in the **Upload Invoice** modal are previewed locally in the browser via `URL.createObjectURL` and are not uploaded to any server.
- Never upload real confidential client invoices into this prototype.

