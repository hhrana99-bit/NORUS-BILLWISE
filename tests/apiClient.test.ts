import assert from 'node:assert/strict';
import test from 'node:test';
import {
  ApiClient,
  ApiClientError,
  buildApiUrl,
  CSRF_COOKIE_NAME,
  CSRF_HEADER_NAME,
  extractCookieValue,
  extractFilenameFromContentDisposition,
  formatApiErrorMessage,
  parseApiErrorResponse,
  resolveApiBaseUrl,
} from '../src/services/apiClient.ts';
import {
  buildInvoiceUpdatePayload,
  mapAuditEventToActivity,
  mapInvoiceDetailDto,
  mapInvoiceSummaryDto,
  mapMonthlyTrendDto,
  mapSupplierSummaryDto,
  mapWorkspaceSettingsDto,
} from '../src/services/apiMappers.ts';
import { sanitizeCsvCell } from '../src/services/reportService.ts';
import { isLatestRequestSeq } from '../src/state/WorkspaceContext.tsx';

test('URL, cookie, and filename helpers behave deterministically', () => {
  assert.equal(resolveApiBaseUrl(''), '/api/v1');
  assert.equal(resolveApiBaseUrl('http://127.0.0.1:8000/'), 'http://127.0.0.1:8000/api/v1');
  assert.equal(resolveApiBaseUrl('http://127.0.0.1:8000/api/v1/'), 'http://127.0.0.1:8000/api/v1');

  assert.equal(
    extractCookieValue('foo=bar; norus_csrf_token=tok%2B123; other=1', CSRF_COOKIE_NAME),
    'tok+123'
  );
  assert.equal(extractCookieValue('', CSRF_COOKIE_NAME), null);

  assert.equal(
    buildApiUrl('/api/v1', '/workspaces/ws-1/invoices', {
      status: 'FLAGGED',
      empty: '',
      missing: undefined,
      page: 2,
    }),
    '/api/v1/workspaces/ws-1/invoices?status=FLAGGED&page=2'
  );

  assert.equal(
    extractFilenameFromContentDisposition(
      'attachment; filename="norus-ws-2026.csv"',
      'fallback.csv'
    ),
    'norus-ws-2026.csv'
  );
  assert.equal(
    extractFilenameFromContentDisposition(null, 'fallback.csv'),
    'fallback.csv'
  );
});

test('parseApiErrorResponse extracts backend error envelope details cleanly', async () => {
  const res = new Response(
    JSON.stringify({
      error: {
        code: 'VARIANCE_ACKNOWLEDGMENT_REQUIRED',
        message: 'Explicit variance acknowledgment is required.',
        details: { variance: '100.00' },
        requestId: 'req-42',
      },
    }),
    {
      status: 409,
      headers: { 'Content-Type': 'application/json' },
    }
  );

  const err = await parseApiErrorResponse(res);
  assert.equal(err instanceof ApiClientError, true);
  assert.equal(err.status, 409);
  assert.equal(err.code, 'VARIANCE_ACKNOWLEDGMENT_REQUIRED');
  assert.equal(err.requestId, 'req-42');
  assert.equal(
    formatApiErrorMessage(err),
    'Explicit variance acknowledgment is required.'
  );
});

test('ApiClient sends credentials: include, injects CSRF token on mutations, and uses single-flight 401 refresh', async () => {
  const origDoc = (globalThis as { document?: unknown }).document;
  (globalThis as { document?: { cookie: string } }).document = {
    cookie: `${CSRF_COOKIE_NAME}=csrf-xyz-789`,
  };

  try {
    const calls: Array<{ url: string; method: string; csrf: string | null; credentials: RequestCredentials | undefined }> = [];
    let refreshed = false;
    let refreshCount = 0;

    const client = new ApiClient({
      baseUrl: '/api/v1',
      fetchImpl: async (input, init) => {
        const url = String(input);
        const method = init?.method ?? 'GET';
        const headers = new Headers(init?.headers);
        calls.push({
          url,
          method,
          csrf: headers.get(CSRF_HEADER_NAME),
          credentials: init?.credentials,
        });

        if (url.endsWith('/auth/login')) {
          return new Response(
            JSON.stringify({
              user: { id: 'u1', email: 'a@b.in', fullName: 'Tester', isActive: true },
              workspaces: [],
              sessionExpiresAt: '2026-12-01T00:00:00Z',
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          );
        }

        if (url.endsWith('/auth/refresh')) {
          refreshCount += 1;
          refreshed = true;
          return new Response(
            JSON.stringify({ refreshed: true, sessionExpiresAt: '2026-12-01T00:00:00Z' }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          );
        }

        if (!refreshed) {
          return new Response(
            JSON.stringify({ error: { code: 'UNAUTHORIZED', message: 'Expired' } }),
            { status: 401, headers: { 'Content-Type': 'application/json' } }
          );
        }

        return new Response(
          JSON.stringify({ ok: true }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      },
    });

    await client.login('a@b.in', 'secret123456');
    assert.equal(calls[0].csrf, null);
    assert.equal(calls[0].credentials, 'include');

    const [r1, r2] = await Promise.all([
      client.requestJson<{ ok: boolean }>('/workspaces/w1/suppliers', {
        method: 'POST',
        body: { name: 'Vendor' },
      }),
      client.requestJson<{ ok: boolean }>('/workspaces/w1/reports/summary'),
    ]);

    assert.equal(r1.ok, true);
    assert.equal(r2.ok, true);
    assert.equal(refreshCount, 1);

    const postCall = calls.find((c) => c.method === 'POST' && c.url.includes('/suppliers'));
    assert.equal(postCall?.csrf, 'csrf-xyz-789');
  } finally {
    (globalThis as { document?: unknown }).document = origDoc;
  }
});

test('ApiClient triggers unauthorizedHandler when refresh fails and maps network errors', async () => {
  let unauthorizedTriggered = 0;
  const failingClient = new ApiClient({
    baseUrl: '/api/v1',
    fetchImpl: async () =>
      new Response(
        JSON.stringify({ error: { code: 'UNAUTHORIZED', message: 'Denied' } }),
        { status: 401, headers: { 'Content-Type': 'application/json' } }
      ),
  });
  failingClient.setUnauthorizedHandler(() => {
    unauthorizedTriggered += 1;
  });

  await assert.rejects(
    () => failingClient.getMe(),
    (err: unknown) => err instanceof ApiClientError && err.status === 401
  );
  assert.equal(unauthorizedTriggered, 1);

  const networkClient = new ApiClient({
    baseUrl: '/api/v1',
    fetchImpl: async () => {
      throw new TypeError('Failed to fetch');
    },
  });
  await assert.rejects(
    () => networkClient.getMe(),
    (err: unknown) => err instanceof ApiClientError && err.code === 'NETWORK_ERROR'
  );
});

test('apiMappers transform DTOs accurately and enforce UPLOADER field verification restrictions', () => {
  const mappedSummary = mapInvoiceSummaryDto({
    id: 'inv-1',
    workspaceId: 'ws-1',
    supplierId: 'sup-1',
    documentId: 'doc-1',
    supplierName: 'Apex Industrial',
    supplierGstin: '27AABCA1234M1Z5',
    buyerName: null,
    buyerGstin: null,
    placeOfSupplyCode: null,
    placeOfSupplyName: null,
    invoiceNumber: 'INV-100',
    normalizedInvoiceNumber: 'INV100',
    invoiceDate: '2026-10-12',
    dueDate: null,
    uploadDate: '2026-10-13',
    financialYear: '2026-27',
    currency: 'INR',
    isReverseCharge: false,
    taxType: 'INTRA_STATE',
    taxableAmount: '1000.00',
    discountAmount: '0.00',
    discountMode: 'BEFORE_TAX',
    cgstAmount: '90.00',
    sgstAmount: '90.00',
    igstAmount: '0.00',
    cessAmount: '0.00',
    taxAmount: '180.00',
    freightAmount: '0.00',
    otherChargesAmount: '0.00',
    roundOffAmount: '0.00',
    totalAmount: '1180.00',
    computedExpectedTotal: '1180.00',
    varianceAmount: '0.00',
    reconciliationStatus: 'MATCHED',
    lineItemsTaxableSum: null,
    lineItemVarianceAmount: null,
    lineItemReconciliationStatus: 'NO_LINE_ITEMS',
    lineItemWarning: null,
    status: 'PENDING_REVIEW',
    duplicateWarning: null,
    reviewerNote: '',
    sourceType: 'DOCUMENT_UPLOAD',
    verifiedByUserId: null,
    verifiedAt: null,
    lineItemCount: 0,
    openFlagCount: 0,
    createdAt: '2026-10-13T10:00:00Z',
    updatedAt: '2026-10-13T10:00:00Z',
  });

  assert.equal(mappedSummary.status, 'Pending Review');
  assert.equal(mappedSummary.totalAmount, 1180);

  const mappedDetail = mapInvoiceDetailDto({
    id: 'inv-1',
    workspaceId: 'ws-1',
    supplierId: 'sup-1',
    documentId: 'doc-1',
    supplierName: 'Apex Industrial',
    supplierGstin: '27AABCA1234M1Z5',
    buyerName: null,
    buyerGstin: null,
    placeOfSupplyCode: null,
    placeOfSupplyName: null,
    invoiceNumber: 'INV-100',
    normalizedInvoiceNumber: 'INV100',
    invoiceDate: '2026-10-12',
    dueDate: null,
    uploadDate: '2026-10-13',
    financialYear: '2026-27',
    currency: 'INR',
    isReverseCharge: false,
    taxType: 'INTRA_STATE',
    taxableAmount: '1000.00',
    discountAmount: '0.00',
    discountMode: 'BEFORE_TAX',
    cgstAmount: '90.00',
    sgstAmount: '90.00',
    igstAmount: '0.00',
    cessAmount: '0.00',
    taxAmount: '180.00',
    freightAmount: '0.00',
    otherChargesAmount: '0.00',
    roundOffAmount: '0.00',
    totalAmount: '1180.00',
    computedExpectedTotal: '1180.00',
    varianceAmount: '0.00',
    reconciliationStatus: 'MATCHED',
    lineItemsTaxableSum: null,
    lineItemVarianceAmount: null,
    lineItemReconciliationStatus: 'NO_LINE_ITEMS',
    lineItemWarning: null,
    status: 'PENDING_REVIEW',
    duplicateWarning: null,
    reviewerNote: '',
    sourceType: 'DOCUMENT_UPLOAD',
    verifiedByUserId: null,
    verifiedAt: null,
    lineItemCount: 0,
    openFlagCount: 0,
    createdAt: '2026-10-13T10:00:00Z',
    updatedAt: '2026-10-13T10:00:00Z',
    document: {
      id: 'doc-1',
      originalFilename: 'bill.pdf',
      mimeType: 'application/pdf',
      byteSize: 2048,
      pageCount: 2,
      scanStatus: 'CLEAN',
      createdAt: '2026-10-13T10:00:00Z',
    },
    lineItems: [],
    fieldVerifications: [],
    reviewFlags: [],
    reconciliation: {
      roundingTolerance: '1.00',
      computedExpectedTotal: '1180.00',
      declaredTotal: '1180.00',
      varianceAmount: '0.00',
      reconciliationStatus: 'MATCHED',
      lineItemsTaxableSum: null,
      lineItemVarianceAmount: null,
      lineItemReconciliationStatus: 'NO_LINE_ITEMS',
      lineItemWarning: null,
      discrepancies: [],
    },
    duplicateMatches: [],
  });

  const draft = {
    ...mappedDetail,
    totalAmount: 1200,
    fieldMeta: {
      ...mappedDetail.fieldMeta,
      totalAmount: { status: 'Verified' as const, evidenceNote: 'Checked' },
      invoiceNumber: { status: 'Flagged' as const, evidenceNote: 'Unclear' },
    },
  };

  const uploaderPayload = buildInvoiceUpdatePayload(mappedDetail, draft, 'UPLOADER');
  assert.equal(uploaderPayload.totalAmount, '1200.00');
  assert.equal(uploaderPayload.fieldVerifications?.length, 1);
  assert.equal(uploaderPayload.fieldVerifications?.[0].fieldKey, 'invoice_number');
  assert.equal(uploaderPayload.fieldVerifications?.[0].status, 'FLAGGED');

  const reviewerPayload = buildInvoiceUpdatePayload(mappedDetail, draft, 'REVIEWER');
  assert.equal(reviewerPayload.fieldVerifications?.length, 2);

  const sup = mapSupplierSummaryDto({
    id: 'sup-1',
    workspaceId: 'ws-1',
    name: 'Vendor One',
    normalizedName: 'vendor one',
    gstin: null,
    pan: null,
    stateCode: '27',
    stateName: 'Maharashtra',
    category: 'IT',
    email: null,
    status: 'NEEDS_VERIFICATION',
    createdAt: '2026-10-13T10:00:00Z',
    updatedAt: '2026-10-13T10:00:00Z',
    totalInvoices: 3,
    totalValue: '4500.50',
    lastInvoiceDate: '2026-10-10',
  });
  assert.equal(sup.status, 'Needs Verification');
  assert.equal(sup.totalValue, 4500.5);

  const wsSettings = mapWorkspaceSettingsDto(
    {
      workspaceId: 'ws-1',
      legalEntityName: 'Firm LLP',
      companyGstin: '27AAAAA0000A1Z5',
      companyPan: 'AAAAA0000A',
      registeredAddress: 'Mumbai',
      requireHumanReview: true,
      enableDuplicateWarnings: true,
      autoFlagTaxMismatch: true,
      roundingTolerance: '1.00',
      defaultCurrency: 'INR',
      financialYear: 'April - March',
      dateFormat: 'DD/MM/YYYY',
      taxRegime: 'India GST (CGST / SGST / IGST)',
      notifyFlaggedInvoices: true,
      notifyDailyDigest: false,
      notifyDuplicateAlerts: true,
      updatedAt: '2026-10-13T10:00:00Z',
    },
    {
      id: 'ws-1',
      organizationId: 'org-1',
      name: 'Client Workspace',
      workspaceCode: 'CW-01',
      isActive: true,
      currentUserRole: 'WORKSPACE_ADMIN',
      createdAt: '2026-10-13T10:00:00Z',
    },
    [
      {
        id: 'org-1',
        name: 'Firm LLP',
        slug: 'firm-llp',
        firmType: 'Tax Consultancy',
        role: 'ORG_OWNER',
      },
    ]
  );
  assert.equal(wsSettings.workspaceName, 'Client Workspace');
  assert.equal(wsSettings.firmType, 'Tax Consultancy');
  assert.equal(wsSettings.roundingTolerance, 1);

  const trend = mapMonthlyTrendDto({
    workspaceId: 'ws-1',
    window: '6m',
    currency: 'INR',
    buckets: [
      {
        monthKey: '2026-10',
        label: 'Oct 26',
        totalCount: 2,
        verifiedCount: 1,
        pendingCount: 1,
        flaggedCount: 0,
        totalValue: '2000.00',
        totalTaxableValue: '1694.92',
        totalGst: '305.08',
      },
    ],
    excludedCount: 0,
    outOfWindowCount: 0,
  });
  assert.equal(trend[0].totalValue, 2000);

  const act = mapAuditEventToActivity({
    id: 'evt-1',
    organizationId: 'org-1',
    workspaceId: 'ws-1',
    actorUserId: 'u-1',
    actorDisplayName: 'Reviewer A',
    eventType: 'invoice.verified',
    entityType: 'invoice',
    entityId: 'inv-1',
    summary: 'Verified invoice',
    tone: 'success',
    metadata: {},
    createdAt: '2026-10-13T10:00:00Z',
  });
  assert.equal(act.invoiceId, 'inv-1');
  assert.equal(act.tone, 'success');
});

test('sanitizeCsvCell catches whitespace-prefixed formulas and isLatestRequestSeq protects against stale workspace switches', () => {
  assert.equal(sanitizeCsvCell('   =CMD()'), "'   =CMD()");
  assert.equal(sanitizeCsvCell(' \t+1+1'), "' \t+1+1");
  assert.equal(sanitizeCsvCell('a\u0000b'), 'ab');
  assert.equal(sanitizeCsvCell(-12.34), '-12.34');

  assert.equal(isLatestRequestSeq(5, 5), true);
  assert.equal(isLatestRequestSeq(5, 4), false);
});
