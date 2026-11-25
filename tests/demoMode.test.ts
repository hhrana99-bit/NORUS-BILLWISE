import assert from 'node:assert/strict';
import test from 'node:test';
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

test('ApiClient blocks all network requests with DEMO_MODE_API_BLOCKED when demo mode is active', async () => {
  let fetchCalls = 0;
  const blockedClient = new ApiClient({
    baseUrl: '/api/v1',
    demoModeChecker: () => true,
    fetchImpl: async () => {
      fetchCalls += 1;
      return new Response('{}', { status: 200 });
    },
  });

  const checks: Array<() => Promise<unknown>> = [
    () => blockedClient.getMe(),
    () => blockedClient.listInvoices('ws-1'),
    () => blockedClient.getReportSummary('ws-1'),
    () => blockedClient.listAuditEvents('ws-1'),
    () => blockedClient.login('user@example.com', 'password123456'),
    () => blockedClient.logout(),
    () =>
      blockedClient.createInvoice('ws-1', {
        invoiceNumber: 'INV-1',
        totalAmount: '100.00',
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
    () => blockedClient.deleteInvoice('ws-1', 'inv-1'),
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

  const exceptions = listDemoReportExceptions({
    flagCategory: 'ARITHMETIC_MISMATCH',
  });
  assert.equal(exceptions.total, 1);
  assert.equal(exceptions.items[0].invoiceId, 'inv-1039');

  const auditVerified = listDemoAuditEvents({ eventType: 'invoice.verified' });
  assert.equal(auditVerified.total, 2);
});
