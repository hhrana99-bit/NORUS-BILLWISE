# NORUS BILLWISE

**Company:** NORUS AI  
**Product:** NORUS BILLWISE  
**Tagline:** *Beyond the World.*  
**Stage:** Task 001 — Frontend Prototype Foundation

NORUS BILLWISE is an AI-powered Invoice Intelligence and Verification Workspace built for Chartered Accountants, accounting firms, bookkeeping professionals, and business finance teams (initial target market: India; future target market: global).

## What Task 001 Includes

- Full B2B SaaS application shell with responsive sidebar and top navigation bar
- **Dashboard:** Real-time KPI cards, GST processing overview, status breakdown, pending review queue, activity log, and supplier summary
- **Invoices:** Searchable, filterable, sortable invoice register plus a local browser demo PDF/image staging modal
- **Review Centre:** Split-screen document preview (page navigation and zoom controls) alongside editable GST fields (`Taxable`, `CGST`, `SGST`, `IGST`, `Total`), live arithmetic reconciliation, per-field verification statuses, source evidence placeholders, and human review actions (`Mark as Verified`, `Flag for Review`, `Save Changes`)
- **Suppliers:** Fictional Indian GSTIN vendor directory with aggregated invoice totals and invoice drill-down
- **Reports:** Verification metrics, monthly stacked volume trend chart, flagged exception report, and working CSV export
- **Settings:** Workspace, company, verification, regional, notification, and privacy preferences persisted locally in `localStorage`

## Tech Stack

- React 19 + TypeScript
- Vite
- Tailwind CSS v4 (`@tailwindcss/vite`)
- Lucide React icons

## Local Development

```bash
npm install
npm run dev
```

To typecheck and build for production:

```bash
npm run lint
npm run build
```

## Important Prototype Caveats

- Uses fictional Indian GST sample data only.
- No backend server, PostgreSQL database, OCR engine, or AI extraction is connected in Task 001.
- Uploaded files in the **Upload Invoice** modal are previewed locally in the browser via `URL.createObjectURL` and are not uploaded to any server.
- Never upload real confidential client invoices into this prototype.
