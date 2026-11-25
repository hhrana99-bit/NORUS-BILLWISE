import {
  HISTORICAL_MONTH_BASELINES,
  INITIAL_INVOICES,
  INITIAL_SETTINGS,
  INITIAL_SUPPLIERS,
} from '../data/mockData';
import {
  buildSupplierSummaries,
  computeArithmeticCheck,
  filterAndSortInvoices,
  type InvoiceSortField,
  type SortDirection,
} from './invoiceService';
import { buildMonthlyTrendStats, computeReportMetrics } from './reportService';
import type {
  ApiAuditEvent,
  ApiDiscrepancy,
  ApiReportExceptionItem,
  ApiReportSummary,
  ApiReviewFlag,
  ApiReviewHistory,
  AuthenticatedUser,
  FlagCategory,
  HistoricalMonthStat,
  Invoice,
  InvoiceStatus,
  OrganizationSummary,
  SupplierSummary,
  WorkspaceMembershipSummary,
  WorkspaceSettings,
} from '../types/domain';

export const DEMO_ORGANIZATION_ID = 'demo-org-001';
export const DEMO_WORKSPACE_ID = 'demo-ws-001';

export const DEMO_USER: AuthenticatedUser = {
  id: 'demo-user-001',
  email: 'demo.reviewer@norus-sample.example',
  fullName: 'Demo Reviewer (Sample)',
  isActive: true,
};

export const DEMO_ORGANIZATIONS: OrganizationSummary[] = [
  {
    id: DEMO_ORGANIZATION_ID,
    name: 'Deshmukh & Associates CA (Sample Demo)',
    slug: 'demo-sample-ca',
    firmType: 'Chartered Accountancy Practice',
    role: 'ORG_OWNER',
  },
];

export const DEMO_WORKSPACES: WorkspaceMembershipSummary[] = [
  {
    workspaceId: DEMO_WORKSPACE_ID,
    organizationId: DEMO_ORGANIZATION_ID,
    name: 'Demo Sample Workspace',
    workspaceCode: 'DEMO-IN-001',
    role: 'VIEWER',
  },
];

const DEMO_FLAGS_BY_INVOICE_ID: Record<string, ApiReviewFlag[]> = {
  'inv-1039': [
    {
      id: 'demo-flag-1039',
      workspaceId: DEMO_WORKSPACE_ID,
      invoiceId: 'inv-1039',
      flagCategory: 'ARITHMETIC_MISMATCH',
      reasonText:
        'Total amount discrepancy: Stated total ₹55,870 differs by ₹1,000 from Taxable + IGST (₹54,870).',
      status: 'OPEN',
      createdByUserId: 'demo-ca-001',
      createdByName: 'CA Ananya Deshmukh (Sample)',
      resolvedByUserId: null,
      resolvedByName: null,
      resolutionNote: null,
      createdAt: '2026-11-16T10:42:00Z',
      resolvedAt: null,
    },
  ],
  'inv-1036': [
    {
      id: 'demo-flag-1036',
      workspaceId: DEMO_WORKSPACE_ID,
      invoiceId: 'inv-1036',
      flagCategory: 'GSTIN_ISSUE',
      reasonText:
        'Supplier GSTIN status pending verification and HSN 4802 12% vs 18% classification check.',
      status: 'OPEN',
      createdByUserId: 'demo-ca-001',
      createdByName: 'CA Ananya Deshmukh (Sample)',
      resolvedByUserId: null,
      resolvedByName: null,
      resolutionNote: null,
      createdAt: '2026-11-08T09:15:00Z',
      resolvedAt: null,
    },
  ],
};

const DEMO_REVIEW_HISTORIES: Record<string, ApiReviewHistory> = {
  'inv-1039': {
    invoiceId: 'inv-1039',
    status: 'FLAGGED',
    actions: [
      {
        id: 'demo-act-1039',
        workspaceId: DEMO_WORKSPACE_ID,
        invoiceId: 'inv-1039',
        actorUserId: 'demo-ca-001',
        actorDisplayName: 'CA Ananya Deshmukh (Sample)',
        actionType: 'FLAG',
        previousStatus: 'PENDING_REVIEW',
        newStatus: 'FLAGGED',
        varianceAcknowledged: false,
        varianceAmountAtAction: '1000.00',
        comment:
          'Hold posting until revised credit/tax invoice is received from vendor.',
        fieldChanges: {},
        createdAt: '2026-11-16T10:42:00Z',
      },
    ],
    flags: DEMO_FLAGS_BY_INVOICE_ID['inv-1039'],
    auditEvents: [],
    totalActions: 1,
    totalFlags: 1,
    totalAuditEvents: 0,
    page: 1,
    pageSize: 50,
  },
  'inv-1036': {
    invoiceId: 'inv-1036',
    status: 'FLAGGED',
    actions: [
      {
        id: 'demo-act-1036',
        workspaceId: DEMO_WORKSPACE_ID,
        invoiceId: 'inv-1036',
        actorUserId: 'demo-ca-001',
        actorDisplayName: 'CA Ananya Deshmukh (Sample)',
        actionType: 'FLAG',
        previousStatus: 'PENDING_REVIEW',
        newStatus: 'FLAGGED',
        varianceAcknowledged: false,
        varianceAmountAtAction: '0.00',
        comment:
          'Confirm vendor GST registration status on portal before GSTR-2B reconciliation.',
        fieldChanges: {},
        createdAt: '2026-11-08T09:15:00Z',
      },
    ],
    flags: DEMO_FLAGS_BY_INVOICE_ID['inv-1036'],
    auditEvents: [],
    totalActions: 1,
    totalFlags: 1,
    totalAuditEvents: 0,
    page: 1,
    pageSize: 50,
  },
  'inv-1038': {
    invoiceId: 'inv-1038',
    status: 'VERIFIED',
    actions: [
      {
        id: 'demo-act-1038',
        workspaceId: DEMO_WORKSPACE_ID,
        invoiceId: 'inv-1038',
        actorUserId: 'demo-assoc-001',
        actorDisplayName: 'Rohan Kulkarni (Sample)',
        actionType: 'VERIFY',
        previousStatus: 'PENDING_REVIEW',
        newStatus: 'VERIFIED',
        varianceAcknowledged: false,
        varianceAmountAtAction: '0.00',
        comment: 'Verified against purchase order PO-26-412.',
        fieldChanges: {},
        createdAt: '2026-11-14T15:10:00Z',
      },
    ],
    flags: [],
    auditEvents: [],
    totalActions: 1,
    totalFlags: 0,
    totalAuditEvents: 0,
    page: 1,
    pageSize: 50,
  },
  'inv-1037': {
    invoiceId: 'inv-1037',
    status: 'VERIFIED',
    actions: [
      {
        id: 'demo-act-1037',
        workspaceId: DEMO_WORKSPACE_ID,
        invoiceId: 'inv-1037',
        actorUserId: 'demo-ca-001',
        actorDisplayName: 'CA Ananya Deshmukh (Sample)',
        actionType: 'VERIFY',
        previousStatus: 'PENDING_REVIEW',
        newStatus: 'VERIFIED',
        varianceAcknowledged: false,
        varianceAmountAtAction: '0.00',
        comment: 'Capital asset addition verified by Senior Partner.',
        fieldChanges: {},
        createdAt: '2026-11-11T11:25:00Z',
      },
    ],
    flags: [],
    auditEvents: [],
    totalActions: 1,
    totalFlags: 0,
    totalAuditEvents: 0,
    page: 1,
    pageSize: 50,
  },
};

const DEMO_AUDIT_EVENTS: ApiAuditEvent[] = [
  {
    id: 'demo-evt-1',
    organizationId: DEMO_ORGANIZATION_ID,
    workspaceId: DEMO_WORKSPACE_ID,
    actorUserId: 'demo-ca-001',
    actorDisplayName: 'CA Ananya Deshmukh (Sample)',
    eventType: 'invoice.flagged',
    entityType: 'invoice',
    entityId: 'inv-1039',
    summary: 'Flagged total discrepancy (₹1,000 variance) on NPL/GUJ/419',
    tone: 'warning',
    metadata: {},
    createdAt: '2026-11-16T10:42:00Z',
  },
  {
    id: 'demo-evt-2',
    organizationId: DEMO_ORGANIZATION_ID,
    workspaceId: DEMO_WORKSPACE_ID,
    actorUserId: 'demo-queue-001',
    actorDisplayName: 'Sample Queue Loader',
    eventType: 'invoice.created',
    entityType: 'invoice',
    entityId: 'inv-1041',
    summary: 'Loaded sample invoice AIC/26-27/1041 into Pending Review queue',
    tone: 'neutral',
    metadata: {},
    createdAt: '2026-11-15T17:18:00Z',
  },
  {
    id: 'demo-evt-3',
    organizationId: DEMO_ORGANIZATION_ID,
    workspaceId: DEMO_WORKSPACE_ID,
    actorUserId: 'demo-assoc-001',
    actorDisplayName: 'Rohan Kulkarni (Sample)',
    eventType: 'invoice.verified',
    entityType: 'invoice',
    entityId: 'inv-1038',
    summary: 'Marked SOS-1192 as Verified after GSTIN & PO check',
    tone: 'success',
    metadata: {},
    createdAt: '2026-11-14T15:10:00Z',
  },
  {
    id: 'demo-evt-4',
    organizationId: DEMO_ORGANIZATION_ID,
    workspaceId: DEMO_WORKSPACE_ID,
    actorUserId: 'demo-ca-001',
    actorDisplayName: 'CA Ananya Deshmukh (Sample)',
    eventType: 'invoice.verified',
    entityType: 'invoice',
    entityId: 'inv-1037',
    summary: 'Approved capital equipment tax invoice DPE/26/0309',
    tone: 'success',
    metadata: {},
    createdAt: '2026-11-11T11:25:00Z',
  },
  {
    id: 'demo-evt-5',
    organizationId: DEMO_ORGANIZATION_ID,
    workspaceId: DEMO_WORKSPACE_ID,
    actorUserId: 'demo-ca-001',
    actorDisplayName: 'CA Ananya Deshmukh (Sample)',
    eventType: 'invoice.flagged',
    entityType: 'invoice',
    entityId: 'inv-1036',
    summary: 'Flagged KPP-TN-071 for GSTIN status and HSN rate verification',
    tone: 'warning',
    metadata: {},
    createdAt: '2026-11-08T09:15:00Z',
  },
];

function enrichDemoInvoice(inv: Invoice): Invoice {
  const arithmetic = computeArithmeticCheck(inv);
  const flags = DEMO_FLAGS_BY_INVOICE_ID[inv.id] ?? [];
  const openFlagCount = flags.filter((f) => f.status === 'OPEN').length;
  const hasVariance = !arithmetic.isBalanced;

  const discrepancies: ApiDiscrepancy[] = hasVariance
    ? [
        {
          code: 'ARITHMETIC_MISMATCH',
          severity: 'warning',
          message: `Declared total (₹${inv.totalAmount.toLocaleString('en-IN')}) differs from computed Taxable + Tax (₹${arithmetic.expectedTotal.toLocaleString('en-IN')}) by ₹${Math.abs(arithmetic.difference).toLocaleString('en-IN')}.`,
          details: {
            expectedTotal: arithmetic.expectedTotal,
            declaredTotal: inv.totalAmount,
            difference: arithmetic.difference,
          },
        },
      ]
    : [];

  return {
    ...inv,
    currency: 'INR',
    computedExpectedTotal: arithmetic.expectedTotal,
    varianceAmount: arithmetic.difference,
    reconciliationStatus: hasVariance ? 'VARIANCE_DETECTED' : 'MATCHED',
    reconciliationDiscrepancies: discrepancies,
    reviewFlags: flags,
    openFlagCount,
    verifiedAt:
      inv.status === 'Verified' ? `${inv.uploadDate}T12:00:00Z` : null,
    duplicateMatches:
      inv.id === 'inv-1040'
        ? [
            {
              invoiceId: 'inv-1034',
              invoiceNumber: 'VCS-2026-791',
              invoiceDate: '2026-10-28',
              totalAmount: '99120.00',
              status: 'VERIFIED',
              matchReasons: ['SIMILAR_TOTAL_WITHIN_45_DAYS'],
            },
          ]
        : [],
    updatedAt: `${inv.uploadDate}T12:00:00Z`,
  };
}

const DEMO_INVOICES: Invoice[] = INITIAL_INVOICES.map(enrichDemoInvoice);

function toApiStatus(status: InvoiceStatus): 'PENDING_REVIEW' | 'VERIFIED' | 'FLAGGED' {
  if (status === 'Verified') return 'VERIFIED';
  if (status === 'Flagged') return 'FLAGGED';
  return 'PENDING_REVIEW';
}

export function getDemoInvoices(): Invoice[] {
  return DEMO_INVOICES;
}

export function getDemoInvoiceDetail(invoiceId: string): Invoice | null {
  return DEMO_INVOICES.find((inv) => inv.id === invoiceId) ?? null;
}

export function getDemoReviewHistory(invoiceId: string): ApiReviewHistory {
  const existing = DEMO_REVIEW_HISTORIES[invoiceId];
  if (existing) return existing;
  const inv = getDemoInvoiceDetail(invoiceId);
  return {
    invoiceId,
    status: inv ? toApiStatus(inv.status) : 'PENDING_REVIEW',
    actions: [],
    flags: [],
    auditEvents: [],
    totalActions: 0,
    totalFlags: 0,
    totalAuditEvents: 0,
    page: 1,
    pageSize: 50,
  };
}

export function listDemoInvoices(params: {
  search?: string;
  status?: 'All' | InvoiceStatus;
  taxType?: 'All' | 'Intra-State (CGST+SGST)' | 'Inter-State (IGST)';
  supplierId?: string | null;
  sortBy?: InvoiceSortField;
  sortDir?: SortDirection;
  page?: number;
  pageSize?: number;
}): { items: Invoice[]; total: number; page: number; pageSize: number } {
  const filtered = filterAndSortInvoices(
    DEMO_INVOICES,
    {
      search: params.search ?? '',
      status: params.status ?? 'All',
      taxType: params.taxType ?? 'All',
      supplierId: params.supplierId ?? undefined,
    },
    params.sortBy ?? 'invoiceDate',
    params.sortDir ?? 'desc'
  );

  const pageSize = Math.max(1, params.pageSize ?? 20);
  const page = Math.max(1, params.page ?? 1);
  const start = (page - 1) * pageSize;

  return {
    items: filtered.slice(start, start + pageSize),
    total: filtered.length,
    page,
    pageSize,
  };
}

export function getDemoSuppliers(): SupplierSummary[] {
  return buildSupplierSummaries(INITIAL_SUPPLIERS, DEMO_INVOICES);
}

export function getDemoSettings(): WorkspaceSettings {
  return {
    ...INITIAL_SETTINGS,
    workspaceName: 'Demo Sample Workspace',
    workspaceCode: 'DEMO-IN-001',
    roundingTolerance: 1,
    defaultCurrency: 'INR',
    requireHumanReview: true,
  };
}

export function getDemoReportSummary(): ApiReportSummary {
  const metrics = computeReportMetrics(DEMO_INVOICES);
  const openFlagCount = DEMO_INVOICES.reduce(
    (sum, inv) => sum + (inv.openFlagCount ?? 0),
    0
  );
  const varianceInvoiceCount = DEMO_INVOICES.filter(
    (inv) => inv.reconciliationStatus === 'VARIANCE_DETECTED'
  ).length;

  return {
    workspaceId: DEMO_WORKSPACE_ID,
    currency: 'INR',
    dateFrom: null,
    dateTo: null,
    totalInvoices: metrics.totalInvoices,
    pendingCount: metrics.pendingCount,
    verifiedCount: metrics.verifiedCount,
    flaggedCount: metrics.flaggedCount,
    verificationRatePercent: metrics.verificationRatePercent,
    pendingValue: metrics.pendingValue.toFixed(2),
    verifiedValue: metrics.verifiedValue.toFixed(2),
    flaggedValue: metrics.flaggedValue.toFixed(2),
    totalTaxableValue: metrics.totalTaxableValue.toFixed(2),
    totalCgst: metrics.totalCgst.toFixed(2),
    totalSgst: metrics.totalSgst.toFixed(2),
    totalIgst: metrics.totalIgst.toFixed(2),
    totalCess: '0.00',
    totalGst: metrics.totalGst.toFixed(2),
    totalInvoiceValue: metrics.totalInvoiceValue.toFixed(2),
    openFlagCount,
    outstandingReviewCount: metrics.pendingCount + metrics.flaggedCount,
    varianceInvoiceCount,
    isStatutoryFilingReport: false,
    disclaimer:
      'DEMO MODE — SAMPLE DATA ONLY: Operational summary derived locally from synthetic fixtures; not live client accounting data or a statutory GST filing.',
  };
}

export function getDemoMonthlyTrend(window: '6m' | '12m' | 'all'): {
  items: HistoricalMonthStat[];
  excludedCount: number;
  outOfWindowCount: number;
  currency: string;
} {
  const liveMonths = buildMonthlyTrendStats(DEMO_INVOICES, {
    windowMonths: 'all',
  });
  const merged = [...HISTORICAL_MONTH_BASELINES, ...liveMonths];
  const sliced = window === '6m' ? merged.slice(-6) : merged;

  return {
    items: sliced,
    excludedCount: 0,
    outOfWindowCount: 0,
    currency: 'INR',
  };
}

export function listDemoReportExceptions(params: {
  search?: string;
  status?: '' | 'PENDING_REVIEW' | 'FLAGGED';
  flagCategory?: '' | FlagCategory;
  page?: number;
  pageSize?: number;
}): { items: ApiReportExceptionItem[]; total: number; page: number; pageSize: number } {
  const exceptionItems: ApiReportExceptionItem[] = DEMO_INVOICES.filter(
    (inv) =>
      inv.status === 'Flagged' ||
      inv.reconciliationStatus === 'VARIANCE_DETECTED' ||
      Boolean(inv.duplicateWarning)
  ).map((inv) => {
    const flags = inv.reviewFlags ?? [];
    const history = DEMO_REVIEW_HISTORIES[inv.id];
    const last = history?.actions[0];
    return {
      invoiceId: inv.id,
      workspaceId: DEMO_WORKSPACE_ID,
      supplierId: inv.supplierId,
      invoiceNumber: inv.invoiceNumber,
      supplierName: inv.supplierName,
      supplierGstin: inv.supplierGstin,
      invoiceDate: inv.invoiceDate,
      uploadDate: inv.uploadDate,
      currency: 'INR',
      totalAmount: inv.totalAmount.toFixed(2),
      varianceAmount: (inv.varianceAmount ?? 0).toFixed(2),
      lineItemVarianceAmount: null,
      status: toApiStatus(inv.status),
      reconciliationStatus: inv.reconciliationStatus ?? 'MATCHED',
      lineItemReconciliationStatus: 'NO_LINE_ITEMS',
      duplicateWarning: inv.duplicateWarning ?? null,
      openFlagCount: inv.openFlagCount ?? 0,
      openFlags: flags
        .filter((f) => f.status === 'OPEN')
        .map((f) => ({
          id: f.id,
          flagCategory: f.flagCategory,
          reasonText: f.reasonText,
          createdByName: f.createdByName,
          createdAt: f.createdAt,
        })),
      lastAction: last
        ? {
            id: last.id,
            actionType: last.actionType,
            actorDisplayName: last.actorDisplayName,
            comment: last.comment,
            createdAt: last.createdAt,
          }
        : null,
      updatedAt: inv.updatedAt ?? `${inv.uploadDate}T12:00:00Z`,
    };
  });

  const q = params.search?.trim().toLowerCase() ?? '';
  const filtered = exceptionItems.filter((item) => {
    if (params.status && item.status !== params.status) return false;
    if (
      params.flagCategory &&
      !item.openFlags.some((f) => f.flagCategory === params.flagCategory)
    ) {
      return false;
    }
    if (q) {
      const hay = `${item.invoiceNumber} ${item.supplierName} ${item.supplierGstin ?? ''}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  const pageSize = Math.max(1, params.pageSize ?? 10);
  const page = Math.max(1, params.page ?? 1);
  const start = (page - 1) * pageSize;

  return {
    items: filtered.slice(start, start + pageSize),
    total: filtered.length,
    page,
    pageSize,
  };
}

export function listDemoAuditEvents(params: {
  eventType?: string;
  page?: number;
  pageSize?: number;
}): { items: ApiAuditEvent[]; total: number; page: number; pageSize: number } {
  const filter = params.eventType?.trim().toLowerCase() ?? '';
  const filtered = filter
    ? DEMO_AUDIT_EVENTS.filter((evt) =>
        evt.eventType.toLowerCase().includes(filter)
      )
    : DEMO_AUDIT_EVENTS;

  const pageSize = Math.max(1, params.pageSize ?? 15);
  const page = Math.max(1, params.page ?? 1);
  const start = (page - 1) * pageSize;

  return {
    items: filtered.slice(start, start + pageSize),
    total: filtered.length,
    page,
    pageSize,
  };
}
