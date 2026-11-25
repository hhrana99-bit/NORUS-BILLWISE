import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { resolveAppViewState } from '../src/App.tsx';
import { resolveDocumentPreviewUrls } from '../src/components/invoices/DocumentPreview.tsx';
import {
  DEMO_MODE_BANNER_TITLE,
  shouldShowDemoBanner,
} from '../src/components/layout/AppShell.tsx';
import {
  DEMO_MODE_DISABLED_ACTION_MESSAGE,
  resolveDemoMode,
} from '../src/config/demoMode.ts';
import {
  ApiClient,
  ApiClientError,
  formatApiErrorMessage,
} from '../src/services/apiClient.ts';
import {
  DEMO_USER,
  DEMO_WORKSPACES,
  DEMO_WORKSPACE_ID,
  getDemoInvoiceDetail,
  getDemoInvoices,
  getDemoMonthlyTrend,
  getDemoReportSummary,
  getDemoReviewHistory,
  getDemoSettings,
  getDemoSuppliers,
  listDemoAuditEvents,
  listDemoInvoices,
  listDemoReportExceptions,
} from '../src/services/demoDataService.ts';
import {
  LOCAL_UI_PREFS_KEY,
  assertMutationsDisabledInDemo,
  getInitialWorkspaceAuthState,
  readLocalUiPrefs,
  writeLocalUiPrefs,
} from '../src/state/WorkspaceContext.tsx';
import {
  DEMO_MODE_PRODUCTION_WARNING,
  checkProductionDemoModeWarning,
} from '../vite.config.ts';

test('resolveDemoMode defaults to false and requires explicit VITE_DEMO_MODE=true', () => {
  assert.equal(resolveDemoMode(undefined), false);
  assert.equal(resolveDemoMode({}), false);
  assert.equal(resolveDemoMode({ VITE_DEMO_MODE: '' }), false);
  assert.equal(resolveDemoMode({ VITE_DEMO_MODE: 'false' }), false);
  assert.equal(resolveDemoMode({ VITE_DEMO_MODE: 'FALSE' }), false);
  assert.equal(resolveDemoMode({ VITE_DEMO_MODE: '1' }), false);
  assert.equal(resolveDemoMode({ VITE_DEMO_MODE: 'yes' }), false);
  assert.equal(resolveDemoMode({ PROD: true, MODE: 'production' }), false);

  assert.equal(resolveDemoMode({ VITE_DEMO_MODE: 'true' }), true);
  assert.equal(resolveDemoMode({ VITE_DEMO_MODE: ' TRUE ' }), true);
  assert.equal(resolveDemoMode({ VITE_DEMO_MODE: true }), true);
});

test('Demo mode bypasses AuthScreen directly to Dashboard while disabled mode enforces normal auth flow', () => {
  const demoInit = getInitialWorkspaceAuthState(true);
  assert.equal(demoInit.authStatus, 'authenticated');
  assert.equal(demoInit.currentUser, DEMO_USER);
  assert.equal(demoInit.workspaces, DEMO_WORKSPACES);
  assert.equal(demoInit.activeWorkspaceId, DEMO_WORKSPACE_ID);
  assert.equal(demoInit.activeRoute, 'dashboard');
  assert.equal(
    resolveAppViewState({
      isDemoMode: true,
      authStatus: demoInit.authStatus,
      workspaceCount: demoInit.workspaces.length,
      activeWorkspaceId: demoInit.activeWorkspaceId,
    }),
    'workspace'
  );

  const normalInit = getInitialWorkspaceAuthState(false, 'ws-stored');
  assert.equal(normalInit.authStatus, 'checking');
  assert.equal(normalInit.currentUser, null);
  assert.equal(normalInit.workspaces.length, 0);
  assert.equal(
    resolveAppViewState({
      isDemoMode: false,
      authStatus: 'checking',
      workspaceCount: 0,
      activeWorkspaceId: null,
    }),
    'checking'
  );
  assert.equal(
    resolveAppViewState({
      isDemoMode: false,
      authStatus: 'unauthenticated',
      workspaceCount: 0,
      activeWorkspaceId: null,
    }),
    'auth'
  );
  assert.equal(
    resolveAppViewState({
      isDemoMode: false,
      authStatus: 'authenticated',
      workspaceCount: 0,
      activeWorkspaceId: null,
    }),
    'no-workspace'
  );
  assert.equal(
    resolveAppViewState({
      isDemoMode: false,
      authStatus: 'authenticated',
      workspaceCount: 1,
      activeWorkspaceId: 'ws-1',
    }),
    'workspace'
  );
});

test('Demo banner renders exclusively when Demo Mode is enabled', () => {
  assert.equal(DEMO_MODE_BANNER_TITLE, 'DEMO MODE — SAMPLE DATA');
  assert.equal(shouldShowDemoBanner(true), true);
  assert.equal(shouldShowDemoBanner(false), false);
});

test('ApiClient blocks all network requests with DEMO_MODE_API_BLOCKED and zero fetch calls when demo mode is active', async () => {
  let fetchCalls = 0;
  const blockedClient = new ApiClient({
    baseUrl: '/api/v1',
    demoModeChecker: () => true,
    fetchImpl: async () => {
      fetchCalls += 1;
      return new Response('{}', { status: 200 });
    },
  });

  const sampleFile = new File(['%PDF-1.4'], 'sample.pdf', {
    type: 'application/pdf',
  });

  const checks: Array<() => Promise<unknown>> = [
    () => blockedClient.getMe(),
    () => blockedClient.getWorkspaceDetail('ws-1'),
    () => blockedClient.getWorkspaceSettings('ws-1'),
    () => blockedClient.listSuppliers('ws-1'),
    () => blockedClient.listInvoices('ws-1'),
    () => blockedClient.getInvoiceDetail('ws-1', 'inv-1'),
    () => blockedClient.getInvoiceReviewHistory('ws-1', 'inv-1'),
    () => blockedClient.getReportSummary('ws-1'),
    () => blockedClient.getMonthlyTrend('ws-1'),
    () => blockedClient.listReportExceptions('ws-1'),
    () => blockedClient.listAuditEvents('ws-1'),
    () => blockedClient.login('user@example.com', 'password123456'),
    () =>
      blockedClient.register({
        fullName: 'Test User',
        email: 'user@example.com',
        password: 'password123456',
        organizationName: 'Test Org',
        firmType: 'CA Practice',
      }),
    () => blockedClient.logout(),
    () => blockedClient.uploadDocument('ws-1', { file: sampleFile }),
    () =>
      blockedClient.createInvoice('ws-1', {
        invoiceNumber: 'INV-1',
        totalAmount: '100.00',
      }),
    () =>
      blockedClient.updateInvoice('ws-1', 'inv-1', {
        reviewerNote: 'Blocked edit',
      }),
    () =>
      blockedClient.verifyInvoice('ws-1', 'inv-1', {
        confirmationNote: 'ok',
      }),
    () =>
      blockedClient.flagInvoice('ws-1', 'inv-1', {
        flagCategory: 'CUSTOM',
        reasonText: 'Check',
      }),
    () =>
      blockedClient.resolveReviewFlag('ws-1', 'flag-1', {
        resolutionStatus: 'RESOLVED',
        resolutionNote: 'Resolved',
      }),
    () => blockedClient.reopenInvoice('ws-1', 'inv-1', 'Reopen'),
    () => blockedClient.deleteInvoice('ws-1', 'inv-1'),
    () =>
      blockedClient.createSupplier('ws-1', {
        name: 'Demo Supplier',
      }),
    () =>
      blockedClient.updateSupplier('ws-1', 'sup-1', {
        status: 'VERIFIED',
      }),
    () =>
      blockedClient.updateWorkspaceSettings('ws-1', {
        legalEntityName: 'Demo Entity',
      }),
    () => blockedClient.downloadReportCsv('ws-1'),
  ];

  for (const runCheck of checks) {
    await assert.rejects(
      runCheck,
      (err: unknown) =>
        err instanceof ApiClientError &&
        err.status === 0 &&
        err.code === 'DEMO_MODE_API_BLOCKED' &&
        formatApiErrorMessage(err) === DEMO_MODE_DISABLED_ACTION_MESSAGE
    );
  }

  assert.equal(fetchCalls, 0);
});

test('DocumentPreview suppresses remote document URLs in Demo Mode even when CLEAN', () => {
  let contentUrlCalls = 0;
  const fakeUrlBuilder = (wsId: string, docId: string, download: boolean) => {
    contentUrlCalls += 1;
    return `/api/v1/workspaces/${wsId}/documents/${docId}/content?download=${download}`;
  };

  const demoPreview = resolveDocumentPreviewUrls({
    isDemoMode: true,
    workspaceId: DEMO_WORKSPACE_ID,
    documentId: 'doc-123',
    documentScanStatus: 'CLEAN',
    getContentUrl: fakeUrlBuilder,
  });
  assert.equal(demoPreview.hasRemoteDocument, false);
  assert.equal(demoPreview.isCleanRemoteDocument, false);
  assert.equal(demoPreview.remotePreviewUrl, null);
  assert.equal(demoPreview.remoteDownloadUrl, null);
  assert.equal(contentUrlCalls, 0);

  const pendingPreview = resolveDocumentPreviewUrls({
    isDemoMode: false,
    workspaceId: 'ws-live',
    documentId: 'doc-123',
    documentScanStatus: 'PENDING',
    getContentUrl: fakeUrlBuilder,
  });
  assert.equal(pendingPreview.hasRemoteDocument, true);
  assert.equal(pendingPreview.isCleanRemoteDocument, false);
  assert.equal(pendingPreview.remotePreviewUrl, null);
  assert.equal(pendingPreview.remoteDownloadUrl, null);
  assert.equal(contentUrlCalls, 0);

  const cleanPreview = resolveDocumentPreviewUrls({
    isDemoMode: false,
    workspaceId: 'ws-live',
    documentId: 'doc-123',
    documentScanStatus: 'CLEAN',
    getContentUrl: fakeUrlBuilder,
  });
  assert.equal(cleanPreview.hasRemoteDocument, true);
  assert.equal(cleanPreview.isCleanRemoteDocument, true);
  assert.equal(
    cleanPreview.remotePreviewUrl,
    '/api/v1/workspaces/ws-live/documents/doc-123/content?download=false'
  );
  assert.equal(
    cleanPreview.remoteDownloadUrl,
    '/api/v1/workspaces/ws-live/documents/doc-123/content?download=true'
  );
  assert.equal(contentUrlCalls, 2);
});

test('Mutating workspace actions throw disabled notice in Demo Mode and localUiPrefs remain isolated', () => {
  assert.throws(
    () => assertMutationsDisabledInDemo(true),
    (err: unknown) =>
      err instanceof Error &&
      err.message === DEMO_MODE_DISABLED_ACTION_MESSAGE
  );
  assert.doesNotThrow(() => assertMutationsDisabledInDemo(false));

  const store = new Map<string, string>();
  const mockStorage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
  };

  assert.deepEqual(readLocalUiPrefs(mockStorage), { compactTables: false });
  writeLocalUiPrefs({ compactTables: true }, mockStorage);
  assert.deepEqual(readLocalUiPrefs(mockStorage), { compactTables: true });
  assert.equal(
    store.get(LOCAL_UI_PREFS_KEY),
    JSON.stringify({ compactTables: true })
  );
  assert.equal(getDemoSettings().workspaceName.length > 0, true);
});

test('demoDataService provides isolated synthetic data across all 6 workspace views', () => {
  assert.equal(DEMO_USER.email.endsWith('.example'), true);
  assert.equal(DEMO_WORKSPACES.length, 1);
  assert.equal(DEMO_WORKSPACES[0].workspaceId, DEMO_WORKSPACE_ID);
  assert.equal(DEMO_WORKSPACES[0].role, 'VIEWER');

  const settings = getDemoSettings();
  assert.equal(settings.requireHumanReview, true);
  assert.equal(settings.workspaceCode, 'DEMO-IN-001');

  const allInvoices = getDemoInvoices();
  assert.equal(allInvoices.length, 10);

  const flaggedPage = listDemoInvoices({ status: 'Flagged', page: 1, pageSize: 20 });
  assert.equal(flaggedPage.total, 2);
  assert.equal(flaggedPage.items[0].reviewFlags?.length, 1);

  const interStatePage = listDemoInvoices({
    taxType: 'Inter-State (IGST)',
    page: 1,
    pageSize: 20,
  });
  assert.equal(
    interStatePage.items.every((inv) => inv.igst > 0),
    true
  );

  const detail1039 = getDemoInvoiceDetail('inv-1039');
  assert.ok(detail1039);
  assert.equal(detail1039.reconciliationStatus, 'VARIANCE_DETECTED');
  assert.equal(detail1039.varianceAmount, 1000);
  assert.equal(getDemoReviewHistory('inv-1039').actions.length, 1);

  const suppliers = getDemoSuppliers();
  assert.equal(suppliers.length, 6);
  const totalSupplierBills = suppliers.reduce((sum, s) => sum + s.totalInvoices, 0);
  assert.equal(totalSupplierBills, allInvoices.length);

  const summary = getDemoReportSummary();
  assert.equal(summary.totalInvoices, allInvoices.length);
  assert.equal(summary.isStatutoryFilingReport, false);
  assert.match(summary.disclaimer, /DEMO MODE — SAMPLE DATA/i);

  const trend6m = getDemoMonthlyTrend('6m');
  assert.equal(trend6m.items.length, 6);
  assert.equal(trend6m.currency, 'INR');
  const trend12m = getDemoMonthlyTrend('12m');
  assert.equal(trend12m.items.length >= 6, true);
  const trendAll = getDemoMonthlyTrend('all');
  assert.equal(trendAll.outOfWindowCount, 0);

  const exceptions = listDemoReportExceptions({
    flagCategory: 'ARITHMETIC_MISMATCH',
  });
  assert.equal(exceptions.total, 1);
  assert.equal(exceptions.items[0].invoiceId, 'inv-1039');

  const auditVerified = listDemoAuditEvents({ eventType: 'invoice.verified' });
  assert.equal(auditVerified.total, 2);
  const auditPage1 = listDemoAuditEvents({ page: 1, pageSize: 2 });
  assert.equal(auditPage1.items.length, 2);
  assert.equal(auditPage1.total >= 2, true);
});

test('Vite production security warning checks effective loadEnv (.env.production/.env.local) and processEnv', () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'norus-vite-env-'));
  try {
    const warnings: string[] = [];
    const emptyEnv = {} as NodeJS.ProcessEnv;

    // 1. Default without env files or processEnv -> no warning
    assert.equal(
      checkProductionDemoModeWarning(
        'production',
        tmpDir,
        (msg) => warnings.push(msg),
        emptyEnv
      ),
      false
    );
    assert.equal(warnings.length, 0);

    // 2. .env.local with VITE_DEMO_MODE=true in production mode -> warns
    fs.writeFileSync(
      path.join(tmpDir, '.env.local'),
      'VITE_DEMO_MODE=true\n',
      'utf8'
    );
    assert.equal(
      checkProductionDemoModeWarning(
        'production',
        tmpDir,
        (msg) => warnings.push(msg),
        emptyEnv
      ),
      true
    );
    assert.equal(warnings.length, 1);
    assert.equal(warnings[0], DEMO_MODE_PRODUCTION_WARNING);

    // 3. Development mode with VITE_DEMO_MODE=true -> no production warning
    assert.equal(
      checkProductionDemoModeWarning(
        'development',
        tmpDir,
        (msg) => warnings.push(msg),
        emptyEnv
      ),
      false
    );
    assert.equal(warnings.length, 1);

    // 4. Shell processEnv VITE_DEMO_MODE=false overrides .env.local -> no warning
    assert.equal(
      checkProductionDemoModeWarning(
        'production',
        tmpDir,
        (msg) => warnings.push(msg),
        { VITE_DEMO_MODE: 'false' } as NodeJS.ProcessEnv
      ),
      false
    );
    assert.equal(warnings.length, 1);

    // 5. .env.production with VITE_DEMO_MODE="TRUE" overrides .env.local=false -> warns
    fs.writeFileSync(
      path.join(tmpDir, '.env.local'),
      'VITE_DEMO_MODE="false"\n',
      'utf8'
    );
    fs.writeFileSync(
      path.join(tmpDir, '.env.production'),
      'VITE_DEMO_MODE="TRUE"\n',
      'utf8'
    );
    assert.equal(
      checkProductionDemoModeWarning(
        'production',
        tmpDir,
        (msg) => warnings.push(msg),
        emptyEnv
      ),
      true
    );
    assert.equal(warnings.length, 2);

    // 6. Shell processEnv VITE_DEMO_MODE=true in production mode -> warns even when .env files are false
    fs.writeFileSync(
      path.join(tmpDir, '.env.production'),
      'VITE_DEMO_MODE="false"\n',
      'utf8'
    );
    assert.equal(
      checkProductionDemoModeWarning(
        'production',
        tmpDir,
        (msg) => warnings.push(msg),
        { VITE_DEMO_MODE: 'true' } as NodeJS.ProcessEnv
      ),
      true
    );
    assert.equal(warnings.length, 3);
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});
