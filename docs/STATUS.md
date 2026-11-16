# STATUS — Project Progress

**Current Milestone:** Task 001.3 — Final Frontend Release Audit & Browser Quality Assurance  
**Status:** Complete (Frontend Audited, Verified in Chromium & CI Configured — Conditionally Ready for Task 002)

## Completed Work in Task 001.3

1. **Real Chromium Browser QA (`375px`, `768px`, `1280px` × all 6 routes)**
   - Verified zero page-level horizontal overflow (`scrollWidth === innerWidth`), zero unlabelled visible icon buttons, zero console errors, zero uncaught page errors, and zero failed internal asset requests across all 18 viewport/route states (`vite preview`).
   - Verified all interactive user flows end-to-end: PDF/PNG local staging & invalid file/missing file validation, search/filter/sort/supplier drill-down, single-item local delete restriction, 3-choice unsaved-edits navigation guard (`Save & Continue`, `Discard Changes`, `Continue Editing`), predefined + custom flag reason & whitespace rejection, arithmetic mismatch verification confirmation gate without silent figure mutation, PDF `<iframe>` zoom scaling & reset, dynamic `6M`/`12M`/`All` monthly trends, CSV formula-injection neutralization in downloaded files, Settings persistence, corrupted `localStorage` recovery, mobile drawer/search `Escape` focus behavior, and `URL.revokeObjectURL` cleanup on delete and demo reset.
2. **Release Audit Defect Fix (`src/pages/ReviewCentrePage.tsx`)**
   - Fixed a real state-effect defect discovered during live Playwright testing where `useEffect([currentInvoice])` immediately cleared `feedbackBanner` after Save/Flag/Verify/Delete Local Draft updates, and removed the 1-frame stale `draft.id` lag when switching invoices via the navigation guard.
3. **GitHub Actions CI (`.github/workflows/ci.yml`)**
   - Added automated CI running `npm ci`, `npm run lint`, `npm test`, and `npm run build` on pushes and PRs targeting `main` and `task-001-2-remediation`.
4. **Clean Install & Automated Verification**
   - Verified `npm ci` (`56` packages, `0` vulnerabilities), `npm run lint` (`tsc --noEmit` strict clean), `npm test` (`11/11` passing), and `npm run build` (`vite build` route-split chunks, zero warnings).

## Verification Coverage Breakdown

- **Verified via Real Chromium Browser + Automated Playwright:** Multi-viewport layout (`375px`/`768px`/`1280px`), lazy route chunk loading, upload validation, invoice register & local delete isolation, Review Centre 3-action unsaved guard, custom flag validation, mismatch safety gate, PDF iframe zoom/reset, `URL.revokeObjectURL` on delete & reset, dynamic monthly chart toggles, downloaded CSV formula sanitization, Settings persistence, corrupted `localStorage` recovery, mobile drawer/search & modal `Escape`/focus handling.
- **Verified via Unit Tests (`tests/services.test.ts` — 11 tests):** Pure service edge cases (`normalizeSupplierName`, `createDemoUploadedInvoice`, `detectDuplicateWarning`, `computeArithmeticCheck`, `sanitizeCsvCell`, `parseStoredInvoicesRaw`/`parseStoredSettingsRaw`, `filterNotificationsBySettings`, `hasUnsavedInvoiceChanges`, `resolveFlagReason`, `buildMonthlyTrendStats`/`parseIsoYearMonth`, `removeLocalStagedInvoice`, `revokeUnusedBlobUrls`/`revokeAllBlobUrls`).
- **Demo-Only / Not Implemented:** Fictional sample GST data only; `localStorage` browser-only persistence; ephemeral `blob:` document previews; no Python FastAPI backend, PostgreSQL database, user auth/RBAC, OCR/AI extraction, or Excel (`.xlsx`) export.

## Remaining Non-Blocking Limitations

- `beforeunload` browser confirmation prompt is wired in React (`ReviewCentrePage.tsx`) and statically verified, but was not triggered via a full native browser unload dialog test.
- Legacy unused exports `HISTORICAL_MONTH_BASELINES` (`src/data/mockData.ts`) and `updateInvoiceStatus` (`src/state/WorkspaceContext.tsx`) remain unused by UI components.
- `.git` is unavailable inside the AI Studio container runtime, so GitHub Actions CI is ready on disk (`.github/workflows/ci.yml`) and will run once synced to `task-001-2-remediation`.
- Note: The AI Studio host preview container occasionally regenerates `bun.lock` automatically; `package-lock.json` is the single intended repository lockfile.


