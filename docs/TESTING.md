# TESTING — Verification & QA Checklist

## 1. Automated Checks

Run in project root:

```bash
npm ci
npm run lint
npm test
npm run build
```

- `npm ci`: Deterministic clean installation via `npm` using `package-lock.json` (zero peer conflicts, 56 packages audited, 0 vulnerabilities).
- `npm run lint`: Runs `tsc --noEmit` with `strict`, `noUnusedLocals`, `noUnusedParameters`, and `noFallthroughCasesInSwitch`.
- `npm test`: Runs `tsx --test tests/*.test.ts` (11 unit tests) covering:
  - Supplier filtering & normalized matching for locally uploaded invoices (`normalizeSupplierName`, `createDemoUploadedInvoice`)
  - Duplicate warning detection & GST arithmetic mismatch calculation (`detectDuplicateWarning`, `computeArithmeticCheck`)
  - CSV formula injection sanitization (`=`, `+`, `-`, `@`, `\t`, `\r`)
  - Schema-versioned `localStorage` validation & malformed JSON recovery
  - Notification preference filtering (`filterNotificationsBySettings`)
  - Unsaved Review Centre edit detection (`hasUnsavedInvoiceChanges`) across scalars, notes, flag reasons, and per-field statuses
  - Flag reason validation & custom reason resolution (`resolveFlagReason`)
  - Dynamic chronological Monthly Trend reporting (`buildMonthlyTrendStats`, `parseIsoYearMonth`), zero-fill gaps, invalid date skipping, and metric parity
  - Local staged invoice deletion (`removeLocalStagedInvoice`) restrictions
  - Object URL revocation lifecycle (`revokeUnusedBlobUrls`, `revokeAllBlobUrls`)
- `npm run build`: Production Vite bundle build (`vite build`) with route-level chunk splitting and zero Vite config warnings.

## 2. GitHub Actions CI (`.github/workflows/ci.yml`)

- **Triggers:** Pushes and pull requests targeting `main` and `task-001-2-remediation`.
- **Environment:** `ubuntu-latest`, Node.js `22` with npm dependency cache.
- **Steps:** `npm ci` -> `npm run lint` -> `npm test` -> `npm run build`. Any non-zero exit code fails the workflow; no secrets or paid services are used.

## 3. Browser QA Coverage (Executed in Task 001.3 via Playwright Chromium)

- **Viewports Tested:** `375x812` (mobile), `768x1024` (tablet), `1280x800` (desktop) across all 6 routes against `vite preview` (`18` viewport/route states verified for zero page-level horizontal overflow, zero unlabelled visible icon buttons, zero console/page errors, and zero failed internal asset requests).
- **Workflows Verified in Browser:**
  1. Upload modal empty/invalid-type rejection, PDF/PNG staging, and prototype notice clarity.
  2. Invoice search, tax-type filter, column sort, supplier drill-down, and `isLocalUpload`-restricted delete confirmation.
  3. Review Centre 3-action unsaved changes guard (`Continue Editing`, `Discard Changes`, `Save & Continue`), persistent feedback banners, predefined + custom flag reason modal (including blank/whitespace rejection), and arithmetic mismatch verification gate without mutating figures.
  4. Document Preview dynamic Settings buyer details (`legalEntityName`) and PDF `<iframe>` zoom scaling (`100%` -> `115%` -> `130%` -> `115%` -> `100%`) + `URL.revokeObjectURL` cleanup on delete and demo reset.
  5. Dynamic Reports (`6M` vs `All` window switching) and downloaded `.csv` formula neutralization check.
  6. Settings persistence across reload, toggle suppression of duplicate/mismatch/notification triggers, and corrupted `localStorage` recovery.
  7. Mobile (`375px`) drawer/search `Escape` focus return and upload modal focus/keyboard checks.
- **Untested / Demo-Only Limitations:** Native browser `beforeunload` dialog trigger was verified via event listener registration rather than browser unload dismissal; real server upload, OCR/AI extraction, and Excel export remain unimplemented demo boundaries until Task 002.


