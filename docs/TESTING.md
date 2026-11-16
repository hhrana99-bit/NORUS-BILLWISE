# TESTING — Verification & QA Checklist (Task 001)

## 1. Automated Static Checks

Run in project root:

```bash
npm run lint
npm run build
```

Both TypeScript typechecking (`tsc --noEmit`) and production Vite bundling (`vite build`) must exit with status `0` and zero warnings/errors.

## 2. Manual Interactive Verification Checklist

1. **Navigation & Responsive Layout**
   - Switch between all 6 sidebar routes: Dashboard, Invoices, Review Centre, Suppliers, Reports, Settings.
   - Verify mobile drawer opens/closes cleanly below `lg` breakpoint and tables scroll horizontally without page overflow.
2. **Global Search & Notifications**
   - Type `NPL` or `Apex` in the TopBar search box; verify matching invoices and suppliers appear and clicking navigates to Review Centre or filtered Invoices.
   - Open Notifications popover, click an unread alert, and verify unread count decrements and navigates to the target screen.
3. **Invoices Page & Local Demo Upload**
   - Test search, status filter (`Flagged`, `Verified`, `Pending Review`), GST type filter (`Intra-State`, `Inter-State`), and column sorting.
   - Click `Upload Invoice`, drop or select a sample PNG/PDF, confirm it stages into `Pending Review` and opens in Review Centre.
4. **Review Centre Split Screen**
   - Test Page 1 / Page 2 navigation and Zoom controls (`-`, `+`, Reset).
   - Focus fields (e.g., `Taxable Amount`, `Total Amount`) and confirm corresponding blocks highlight on the simulated invoice preview.
   - Edit numeric values on `NPL/GUJ/419` to resolve the ₹1,000 variance (`54870`), click `Mark as Verified`, and confirm Dashboard KPIs, Reports completion rate, and Activity log update immediately.
5. **Suppliers, Reports & Settings**
   - Click `View` on a supplier row and confirm Invoices opens filtered to that supplier.
   - Click `Export CSV Report` on Reports and verify a valid `.csv` file downloads.
   - Edit Workspace Name in Settings, save, verify TopBar updates immediately, and test `Reset Demo Data`.
