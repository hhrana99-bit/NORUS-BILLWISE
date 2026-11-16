import assert from 'node:assert/strict';
import test from 'node:test';
import {
  INITIAL_INVOICES,
  INITIAL_NOTIFICATIONS,
  INITIAL_SETTINGS,
  INITIAL_SUPPLIERS,
} from '../src/data/mockData.ts';
import {
  buildSupplierSummaries,
  computeArithmeticCheck,
  createDemoUploadedInvoice,
  CUSTOM_FLAG_OPTION,
  detectDuplicateWarning,
  filterAndSortInvoices,
  hasUnsavedInvoiceChanges,
  normalizeSupplierName,
  PREDEFINED_FLAG_REASONS,
  removeLocalStagedInvoice,
  resolveFlagReason,
} from '../src/services/invoiceService.ts';
import {
  isBlobObjectUrl,
  revokeAllBlobUrls,
  revokeUnusedBlobUrls,
} from '../src/services/objectUrlService.ts';
import {
  buildInvoicesCsv,
  buildMonthlyTrendStats,
  computeReportMetrics,
  parseIsoYearMonth,
  sanitizeCsvCell,
} from '../src/services/reportService.ts';
import {
  parseStoredInvoicesRaw,
  parseStoredSettingsRaw,
  STORAGE_SCHEMA_VERSION,
} from '../src/services/storageService.ts';
import { filterNotificationsBySettings } from '../src/state/WorkspaceContext.tsx';

test('supplier filtering matches both existing supplier IDs and locally uploaded invoices by normalized name', () => {
  assert.equal(
    normalizeSupplierName('  Apex   Industrial Components Pvt. Ltd. '),
    'apex industrial components pvt. ltd.'
  );

  const localUnlinked = {
    ...createDemoUploadedInvoice({
      file: { name: 'local-bill.pdf', type: 'application/pdf' } as File,
      previewUrl: 'blob:demo',
      supplierName: '  apex  industrial components pvt. ltd. ',
      invoiceNumber: 'AIC/LOCAL/901',
    }),
    supplierId: 'sup-local',
  };

  const combined = [localUnlinked, ...INITIAL_INVOICES];
  const targetSupplier = INITIAL_SUPPLIERS[0];

  const filtered = filterAndSortInvoices(
    combined,
    {
      search: '',
      status: 'All',
      taxType: 'All',
      supplierId: targetSupplier.id,
      supplierName: targetSupplier.name,
    },
    'invoiceDate',
    'desc'
  );

  assert.equal(filtered.some((inv) => inv.id === localUnlinked.id), true);
  assert.equal(filtered.length, 3);

  const summaries = buildSupplierSummaries(INITIAL_SUPPLIERS, combined);
  const apexSummary = summaries.find((s) => s.id === targetSupplier.id);
  assert.equal(apexSummary?.totalInvoices, 3);
});

test('createDemoUploadedInvoice links known supplier when name matches', () => {
  const created = createDemoUploadedInvoice({
    file: { name: 'sample.png', type: 'image/png' } as File,
    previewUrl: 'blob:sample',
    supplierName: 'Vindhya Cloud & Infrastructure Services',
    invoiceNumber: 'VCS-LOCAL-1',
    suppliers: INITIAL_SUPPLIERS,
  });

  assert.equal(created.supplierId, 'sup-002');
  assert.equal(created.supplierGstin, '29AAACV9102K1Z8');
});

test('detectDuplicateWarning and computeArithmeticCheck identify duplicates and tax mismatches', () => {
  const duplicateByNumber = detectDuplicateWarning(
    {
      id: 'inv-new',
      invoiceNumber: 'AIC/26-27/1041',
      supplierName: 'Apex Industrial Components Pvt. Ltd.',
      totalAmount: 5000,
    },
    INITIAL_INVOICES
  );
  assert.ok(duplicateByNumber?.includes('Duplicate') || duplicateByNumber?.includes('duplicate'));

  const unbalanced = computeArithmeticCheck(INITIAL_INVOICES[2]);
  assert.equal(unbalanced.isBalanced, false);
  assert.equal(unbalanced.difference, 1000);

  const balanced = computeArithmeticCheck(INITIAL_INVOICES[0]);
  assert.equal(balanced.isBalanced, true);
  assert.equal(balanced.difference, 0);
});

test('sanitizeCsvCell neutralizes formula injection prefixes while preserving normal text and numbers', () => {
  assert.equal(sanitizeCsvCell('=SUM(A1:A2)'), "'=SUM(A1:A2)");
  assert.equal(sanitizeCsvCell('+cmd|"/C calc"!A0'), "\"'+cmd|\"\"/C calc\"\"!A0\"");
  assert.equal(sanitizeCsvCell('-2+3'), "'-2+3");
  assert.equal(sanitizeCsvCell('@SUM(1+1)'), "'@SUM(1+1)");
  assert.equal(sanitizeCsvCell('\t=1+1'), "'\t=1+1");
  assert.equal(sanitizeCsvCell('\r=1+1'), "\"'\r=1+1\"");

  assert.equal(sanitizeCsvCell('Sahyadri Office Supplies Co.'), 'Sahyadri Office Supplies Co.');
  assert.equal(sanitizeCsvCell('Apex, Pvt. Ltd.'), '"Apex, Pvt. Ltd."');
  assert.equal(sanitizeCsvCell(147500), '147500');
  assert.equal(sanitizeCsvCell(-250.5), '-250.5');

  const csv = buildInvoicesCsv(
    [
      {
        ...INITIAL_INVOICES[0],
        supplierName: '=HYPERLINK("https://evil.example","Click")',
        reviewerNote: '+1+1',
      },
    ],
    '=Workspace'
  );
  const lines = csv.split('\n');
  assert.equal(lines.length, 2);
  assert.ok(lines[1].startsWith("'=Workspace,"));
  assert.ok(lines[1].includes("\"'=HYPERLINK("));
  assert.ok(lines[1].includes("'+1+1"));
  assert.ok(lines[1].includes(',147500.00,'));
});

test('storageService validates schema version, handles malformed JSON, and recovers safely', () => {
  assert.equal(parseStoredInvoicesRaw(null), null);
  assert.equal(parseStoredInvoicesRaw('{not valid json'), null);
  assert.equal(parseStoredSettingsRaw('{not valid json'), null);

  assert.equal(
    parseStoredInvoicesRaw(JSON.stringify(INITIAL_INVOICES)),
    null
  );
  assert.equal(
    parseStoredInvoicesRaw(
      JSON.stringify({ schemaVersion: 1, data: INITIAL_INVOICES })
    ),
    null
  );
  assert.equal(
    parseStoredSettingsRaw(
      JSON.stringify({ schemaVersion: 1, data: INITIAL_SETTINGS })
    ),
    null
  );

  const corruptedInvoice = { ...INITIAL_INVOICES[0], totalAmount: 'NaN' };
  assert.equal(
    parseStoredInvoicesRaw(
      JSON.stringify({
        schemaVersion: STORAGE_SCHEMA_VERSION,
        data: [corruptedInvoice],
      })
    ),
    null
  );

  const invalidSettings = { ...INITIAL_SETTINGS, requireHumanReview: false };
  assert.equal(
    parseStoredSettingsRaw(
      JSON.stringify({
        schemaVersion: STORAGE_SCHEMA_VERSION,
        data: invalidSettings,
      })
    ),
    null
  );

  const localInv = {
    ...INITIAL_INVOICES[0],
    isLocalUpload: true,
    localPreviewUrl: 'blob:http://localhost/abc',
  };
  const parsedInvoices = parseStoredInvoicesRaw(
    JSON.stringify({
      schemaVersion: STORAGE_SCHEMA_VERSION,
      data: [localInv],
    })
  );
  assert.equal(parsedInvoices?.length, 1);
  assert.equal(parsedInvoices?.[0].localPreviewUrl, undefined);

  const parsedSettings = parseStoredSettingsRaw(
    JSON.stringify({
      schemaVersion: STORAGE_SCHEMA_VERSION,
      data: INITIAL_SETTINGS,
    })
  );
  assert.equal(parsedSettings?.workspaceName, INITIAL_SETTINGS.workspaceName);
});

test('filterNotificationsBySettings respects notification toggles', () => {
  const allEnabled = filterNotificationsBySettings(INITIAL_NOTIFICATIONS, {
    notifyFlaggedInvoices: true,
    notifyDuplicateAlerts: true,
    notifyDailyDigest: true,
  });
  assert.equal(allEnabled.length, 3);

  const onlyFlagged = filterNotificationsBySettings(INITIAL_NOTIFICATIONS, {
    notifyFlaggedInvoices: true,
    notifyDuplicateAlerts: false,
    notifyDailyDigest: false,
  });
  assert.equal(onlyFlagged.length, 1);
  assert.equal(onlyFlagged[0].category, 'flagged');

  const noneEnabled = filterNotificationsBySettings(INITIAL_NOTIFICATIONS, {
    notifyFlaggedInvoices: false,
    notifyDuplicateAlerts: false,
    notifyDailyDigest: false,
  });
  assert.equal(noneEnabled.length, 0);
});

test('hasUnsavedInvoiceChanges detects scalar, note, flagReason, and fieldMeta edits and resets when reverted', () => {
  const original = INITIAL_INVOICES[0];
  const identicalCopy = {
    ...original,
    fieldMeta: { ...original.fieldMeta },
  };
  assert.equal(hasUnsavedInvoiceChanges(original, identicalCopy), false);

  const editedAmount = { ...identicalCopy, taxableAmount: original.taxableAmount + 100 };
  assert.equal(hasUnsavedInvoiceChanges(original, editedAmount), true);

  const revertedAmount = { ...editedAmount, taxableAmount: original.taxableAmount };
  assert.equal(hasUnsavedInvoiceChanges(original, revertedAmount), false);

  const editedNote = { ...identicalCopy, reviewerNote: 'Updated audit comment' };
  assert.equal(hasUnsavedInvoiceChanges(original, editedNote), true);

  const editedMeta = {
    ...identicalCopy,
    fieldMeta: {
      ...identicalCopy.fieldMeta,
      cgst: { ...identicalCopy.fieldMeta.cgst, status: 'Flagged' as const },
    },
  };
  assert.equal(hasUnsavedInvoiceChanges(original, editedMeta), true);

  const differentId = { ...identicalCopy, id: 'inv-other' };
  assert.equal(hasUnsavedInvoiceChanges(original, differentId), false);
  assert.equal(hasUnsavedInvoiceChanges(undefined, identicalCopy), false);
});

test('resolveFlagReason supports predefined reasons, optional detail, custom input, and rejects empty whitespace', () => {
  const predefined = resolveFlagReason({
    selectedReason: PREDEFINED_FLAG_REASONS[0],
    customReason: '',
  });
  assert.deepEqual(predefined, {
    ok: true,
    reason: PREDEFINED_FLAG_REASONS[0],
  });

  const predefinedWithDetail = resolveFlagReason({
    selectedReason: PREDEFINED_FLAG_REASONS[1],
    customReason: '  Matches Jan bill  ',
  });
  assert.deepEqual(predefinedWithDetail, {
    ok: true,
    reason: `${PREDEFINED_FLAG_REASONS[1]} — Matches Jan bill`,
  });

  const whitespaceDetail = resolveFlagReason({
    selectedReason: PREDEFINED_FLAG_REASONS[0],
    customReason: '   ',
  });
  assert.equal(whitespaceDetail.ok, false);

  const customValid = resolveFlagReason({
    selectedReason: CUSTOM_FLAG_OPTION,
    customReason: '  Missing e-Way bill reference  ',
  });
  assert.deepEqual(customValid, {
    ok: true,
    reason: 'Missing e-Way bill reference',
  });

  const customWhitespace = resolveFlagReason({
    selectedReason: CUSTOM_FLAG_OPTION,
    customReason: '   \n\t  ',
  });
  assert.equal(customWhitespace.ok, false);
});

test('buildMonthlyTrendStats derives dynamic chronological months, handles empty windows and invalid dates, and matches report metrics', () => {
  assert.equal(parseIsoYearMonth(''), null);
  assert.equal(parseIsoYearMonth('2026-02-30'), null);
  assert.equal(parseIsoYearMonth('2026-13-01'), null);
  assert.equal(parseIsoYearMonth('not-a-date'), null);
  assert.deepEqual(parseIsoYearMonth('2026-02-15'), {
    year: 2026,
    month: 2,
    monthKey: '2026-02',
  });

  assert.deepEqual(buildMonthlyTrendStats([]), []);

  const spanInvoices = [
    {
      ...INITIAL_INVOICES[0],
      id: 'inv-sep',
      invoiceDate: '2025-09-12',
      status: 'Verified' as const,
      totalAmount: 10000,
    },
    {
      ...INITIAL_INVOICES[1],
      id: 'inv-feb',
      invoiceDate: '2026-02-04',
      status: 'Pending Review' as const,
      totalAmount: 25000,
    },
    {
      ...INITIAL_INVOICES[2],
      id: 'inv-bad-date',
      invoiceDate: '2026-02-31',
      status: 'Flagged' as const,
      totalAmount: 9999,
    },
  ];

  const sixMonthWindow = buildMonthlyTrendStats(spanInvoices, { windowMonths: 6 });
  assert.deepEqual(
    sixMonthWindow.map((m) => m.monthKey),
    ['2025-09', '2025-10', '2025-11', '2025-12', '2026-01', '2026-02']
  );
  assert.equal(sixMonthWindow[0].totalCount, 1);
  assert.equal(sixMonthWindow[0].verifiedCount, 1);
  assert.equal(sixMonthWindow[2].totalCount, 0);
  assert.equal(sixMonthWindow[2].totalValue, 0);
  assert.equal(sixMonthWindow[5].totalCount, 1);
  assert.equal(sixMonthWindow[5].pendingCount, 1);

  const initialAll = buildMonthlyTrendStats(INITIAL_INVOICES, { windowMonths: 'all' });
  const initialMetrics = computeReportMetrics(INITIAL_INVOICES);
  const sumCounts = initialAll.reduce((s, m) => s + m.totalCount, 0);
  const sumValues = initialAll.reduce((s, m) => s + m.totalValue, 0);
  assert.equal(sumCounts, initialMetrics.totalInvoices);
  assert.equal(sumValues, initialMetrics.totalInvoiceValue);
});

test('removeLocalStagedInvoice deletes only isLocalUpload invoices and leaves seeded records intact', () => {
  const localInv = createDemoUploadedInvoice({
    file: { name: 'local.pdf', type: 'application/pdf' } as File,
    previewUrl: 'blob:http://localhost/local-1',
    supplierName: 'Local Vendor',
    invoiceNumber: 'LOC-01',
  });
  const list = [localInv, ...INITIAL_INVOICES];

  const attemptSeeded = removeLocalStagedInvoice(list, INITIAL_INVOICES[0].id);
  assert.equal(attemptSeeded.removed, null);
  assert.equal(attemptSeeded.updated.length, list.length);

  const attemptLocal = removeLocalStagedInvoice(list, localInv.id);
  assert.equal(attemptLocal.removed?.id, localInv.id);
  assert.equal(attemptLocal.updated.length, INITIAL_INVOICES.length);
  assert.equal(
    attemptLocal.updated.some((inv) => inv.id === localInv.id),
    false
  );
});

test('objectUrlService revokes only orphaned or cleared blob URLs and ignores non-blob URLs', () => {
  assert.equal(isBlobObjectUrl('blob:http://localhost/1'), true);
  assert.equal(isBlobObjectUrl('https://example.com/file.pdf'), false);
  assert.equal(isBlobObjectUrl(undefined), false);

  const localA = createDemoUploadedInvoice({
    file: { name: 'a.pdf', type: 'application/pdf' } as File,
    previewUrl: 'blob:http://localhost/a',
    supplierName: 'Vendor A',
    invoiceNumber: 'A-1',
  });
  const localB = createDemoUploadedInvoice({
    file: { name: 'b.png', type: 'image/png' } as File,
    previewUrl: 'blob:http://localhost/b',
    supplierName: 'Vendor B',
    invoiceNumber: 'B-1',
  });
  const nonBlob = {
    ...INITIAL_INVOICES[0],
    localPreviewUrl: 'https://example.com/ignored.pdf',
  };

  const revokedUnused: string[] = [];
  revokeUnusedBlobUrls(
    [localA, localB, nonBlob],
    [localB, nonBlob],
    (url) => revokedUnused.push(url)
  );
  assert.deepEqual(revokedUnused, ['blob:http://localhost/a']);

  const revokedAll: string[] = [];
  revokeAllBlobUrls([localA, localB, nonBlob], (url) => revokedAll.push(url));
  assert.deepEqual(revokedAll, [
    'blob:http://localhost/a',
    'blob:http://localhost/b',
  ]);
});

