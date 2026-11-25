import type {
  ActivityEvent,
  ApiAuditEvent,
  FieldVerificationStatus,
  HistoricalMonthStat,
  Invoice,
  InvoiceFieldKey,
  InvoiceFieldMeta,
  InvoiceStatus,
  OrganizationSummary,
  SupplierStatus,
  SupplierSummary,
  WorkspaceRole,
  WorkspaceSettings,
} from '../types/domain';
import type {
  InvoiceDetailDto,
  InvoiceSummaryDto,
  InvoiceUpdatePayload,
  MonthlyTrendResponseDto,
  SupplierSummaryDto,
  WorkspaceDetailDto,
  WorkspaceSettingsDto,
} from './apiClient';

const UI_FIELD_KEYS: InvoiceFieldKey[] = [
  'supplierName',
  'supplierGstin',
  'invoiceNumber',
  'invoiceDate',
  'taxableAmount',
  'cgst',
  'sgst',
  'igst',
  'totalAmount',
];

const UI_TO_API_FIELD_KEY: Record<InvoiceFieldKey, string> = {
  supplierName: 'supplier_name',
  supplierGstin: 'supplier_gstin',
  invoiceNumber: 'invoice_number',
  invoiceDate: 'invoice_date',
  taxableAmount: 'taxable_amount',
  cgst: 'cgst_amount',
  sgst: 'sgst_amount',
  igst: 'igst_amount',
  totalAmount: 'total_amount',
};

const API_TO_UI_FIELD_KEY: Record<string, InvoiceFieldKey> = {
  supplier_name: 'supplierName',
  supplier_name_snapshot: 'supplierName',
  supplierName: 'supplierName',
  supplier_gstin: 'supplierGstin',
  supplier_gstin_snapshot: 'supplierGstin',
  supplierGstin: 'supplierGstin',
  invoice_number: 'invoiceNumber',
  invoiceNumber: 'invoiceNumber',
  invoice_date: 'invoiceDate',
  invoiceDate: 'invoiceDate',
  taxable_amount: 'taxableAmount',
  taxableAmount: 'taxableAmount',
  cgst_amount: 'cgst',
  cgst: 'cgst',
  sgst_amount: 'sgst',
  sgst: 'sgst',
  igst_amount: 'igst',
  igst: 'igst',
  total_amount: 'totalAmount',
  totalAmount: 'totalAmount',
};

export function mapApiInvoiceStatus(
  status: 'PENDING_REVIEW' | 'VERIFIED' | 'FLAGGED'
): InvoiceStatus {
  if (status === 'VERIFIED') return 'Verified';
  if (status === 'FLAGGED') return 'Flagged';
  return 'Pending Review';
}

export function mapUiInvoiceStatusToApi(
  status: InvoiceStatus
): 'PENDING_REVIEW' | 'VERIFIED' | 'FLAGGED' {
  if (status === 'Verified') return 'VERIFIED';
  if (status === 'Flagged') return 'FLAGGED';
  return 'PENDING_REVIEW';
}

export function mapApiFieldStatus(
  status: 'VERIFIED' | 'NEEDS_REVIEW' | 'FLAGGED'
): FieldVerificationStatus {
  if (status === 'VERIFIED') return 'Verified';
  if (status === 'FLAGGED') return 'Flagged';
  return 'Needs Review';
}

export function mapUiFieldStatusToApi(
  status: FieldVerificationStatus
): 'VERIFIED' | 'NEEDS_REVIEW' | 'FLAGGED' {
  if (status === 'Verified') return 'VERIFIED';
  if (status === 'Flagged') return 'FLAGGED';
  return 'NEEDS_REVIEW';
}

export function mapApiSupplierStatus(
  status: 'VERIFIED' | 'NEEDS_VERIFICATION' | 'FLAGGED'
): SupplierStatus {
  if (status === 'VERIFIED') return 'Verified';
  if (status === 'FLAGGED') return 'Flagged';
  return 'Needs Verification';
}

export function mapUiSupplierStatusToApi(
  status: SupplierStatus
): 'VERIFIED' | 'NEEDS_VERIFICATION' | 'FLAGGED' {
  if (status === 'Verified') return 'VERIFIED';
  if (status === 'Flagged') return 'FLAGGED';
  return 'NEEDS_VERIFICATION';
}

function defaultFieldMeta(defaultStatus: FieldVerificationStatus): Record<
  InvoiceFieldKey,
  InvoiceFieldMeta
> {
  return UI_FIELD_KEYS.reduce((acc, key) => {
    acc[key] = {
      status: defaultStatus,
      evidenceNote:
        defaultStatus === 'Verified'
          ? 'Verified in Review Centre.'
          : 'Awaiting human review against source document.',
    };
    return acc;
  }, {} as Record<InvoiceFieldKey, InvoiceFieldMeta>);
}

function toMoneyNumber(raw: string | number | null | undefined): number {
  if (raw === null || raw === undefined || raw === '') return 0;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function mapInvoiceSummaryDto(dto: InvoiceSummaryDto): Invoice {
  const uiStatus = mapApiInvoiceStatus(dto.status);
  const defaultFieldStatus: FieldVerificationStatus =
    uiStatus === 'Verified' ? 'Verified' : 'Needs Review';

  return {
    id: dto.id,
    invoiceNumber: dto.invoiceNumber,
    supplierId: dto.supplierId ?? '',
    supplierName: dto.supplierName,
    supplierGstin: dto.supplierGstin ?? '',
    invoiceDate: dto.invoiceDate ?? '',
    uploadDate: dto.uploadDate,
    taxableAmount: toMoneyNumber(dto.taxableAmount),
    cgst: toMoneyNumber(dto.cgstAmount),
    sgst: toMoneyNumber(dto.sgstAmount),
    igst: toMoneyNumber(dto.igstAmount),
    totalAmount: toMoneyNumber(dto.totalAmount),
    status: uiStatus,
    reviewerNote: dto.reviewerNote ?? '',
    duplicateWarning: dto.duplicateWarning ?? undefined,
    documentFileName: dto.documentId ? 'Uploaded Invoice Document' : 'Manual Entry Record',
    documentPageCount: 1,
    isLocalUpload: false,
    lineItems: [],
    fieldMeta: defaultFieldMeta(defaultFieldStatus),
    currency: dto.currency,
    cessAmount: toMoneyNumber(dto.cessAmount),
    roundOffAmount: toMoneyNumber(dto.roundOffAmount),
    discountAmount: toMoneyNumber(dto.discountAmount),
    freightAmount: toMoneyNumber(dto.freightAmount),
    otherChargesAmount: toMoneyNumber(dto.otherChargesAmount),
    dueDate: dto.dueDate,
    documentId: dto.documentId,
    computedExpectedTotal: toMoneyNumber(dto.computedExpectedTotal),
    varianceAmount: toMoneyNumber(dto.varianceAmount),
    reconciliationStatus: dto.reconciliationStatus,
    lineItemsTaxableSum:
      dto.lineItemsTaxableSum !== null
        ? toMoneyNumber(dto.lineItemsTaxableSum)
        : null,
    lineItemVarianceAmount:
      dto.lineItemVarianceAmount !== null
        ? toMoneyNumber(dto.lineItemVarianceAmount)
        : null,
    lineItemReconciliationStatus: dto.lineItemReconciliationStatus,
    lineItemWarning: dto.lineItemWarning,
    openFlagCount: dto.openFlagCount,
    verifiedByUserId: dto.verifiedByUserId,
    verifiedAt: dto.verifiedAt,
    updatedAt: dto.updatedAt,
  };
}

export function mapInvoiceDetailDto(dto: InvoiceDetailDto): Invoice {
  const base = mapInvoiceSummaryDto(dto);
  const fieldMeta = { ...base.fieldMeta };

  for (const fv of dto.fieldVerifications) {
    const uiKey = API_TO_UI_FIELD_KEY[fv.fieldKey];
    if (!uiKey) continue;
    fieldMeta[uiKey] = {
      status: mapApiFieldStatus(fv.status),
      evidenceNote: fv.evidenceNote || fieldMeta[uiKey].evidenceNote,
    };
  }

  const latestOpenFlag = [...dto.reviewFlags]
    .reverse()
    .find((flag) => flag.status === 'OPEN');

  return {
    ...base,
    flagReason: latestOpenFlag?.reasonText,
    documentFileName: dto.document?.originalFilename ?? base.documentFileName,
    documentPageCount: dto.document?.pageCount ?? 1,
    documentMimeType: dto.document?.mimeType ?? null,
    documentScanStatus: dto.document?.scanStatus ?? null,
    lineItems: dto.lineItems.map((li) => ({
      id: li.id,
      description: li.description,
      hsnSac: li.hsnSac ?? '',
      quantity: toMoneyNumber(li.quantity),
      unitPrice: toMoneyNumber(li.unitPrice),
      taxRatePercent: toMoneyNumber(li.taxRatePercent),
      taxableValue: toMoneyNumber(li.taxableValue),
    })),
    fieldMeta,
    reconciliationDiscrepancies: dto.reconciliation.discrepancies,
    duplicateMatches: dto.duplicateMatches,
    reviewFlags: dto.reviewFlags,
  };
}

export function buildInvoiceUpdatePayload(
  original: Invoice,
  draft: Invoice,
  role: WorkspaceRole | null
): InvoiceUpdatePayload {
  const payload: InvoiceUpdatePayload = {};

  if (draft.supplierName !== original.supplierName) {
    payload.supplierName = draft.supplierName;
  }
  if (draft.supplierGstin !== original.supplierGstin) {
    payload.supplierGstin = draft.supplierGstin.trim() || null;
  }
  if (draft.invoiceNumber !== original.invoiceNumber) {
    payload.invoiceNumber = draft.invoiceNumber;
  }
  if (draft.invoiceDate !== original.invoiceDate) {
    payload.invoiceDate = draft.invoiceDate.trim() || null;
  }
  if (draft.taxableAmount !== original.taxableAmount) {
    payload.taxableAmount = draft.taxableAmount.toFixed(2);
  }
  if (draft.cgst !== original.cgst) {
    payload.cgstAmount = draft.cgst.toFixed(2);
  }
  if (draft.sgst !== original.sgst) {
    payload.sgstAmount = draft.sgst.toFixed(2);
  }
  if (draft.igst !== original.igst) {
    payload.igstAmount = draft.igst.toFixed(2);
  }
  if (draft.totalAmount !== original.totalAmount) {
    payload.totalAmount = draft.totalAmount.toFixed(2);
  }
  if (draft.reviewerNote !== original.reviewerNote) {
    payload.reviewerNote = draft.reviewerNote;
  }

  const changedFieldVerifications: NonNullable<
    InvoiceUpdatePayload['fieldVerifications']
  > = [];
  for (const uiKey of UI_FIELD_KEYS) {
    const origMeta = original.fieldMeta[uiKey];
    const draftMeta = draft.fieldMeta[uiKey];
    if (
      origMeta.status !== draftMeta.status ||
      origMeta.evidenceNote !== draftMeta.evidenceNote
    ) {
      const apiStatus = mapUiFieldStatusToApi(draftMeta.status);
      if (role === 'UPLOADER' && apiStatus === 'VERIFIED') {
        continue;
      }
      changedFieldVerifications.push({
        fieldKey: UI_TO_API_FIELD_KEY[uiKey],
        status: apiStatus,
        evidenceNote: draftMeta.evidenceNote,
      });
    }
  }
  if (changedFieldVerifications.length > 0) {
    payload.fieldVerifications = changedFieldVerifications;
  }

  return payload;
}

export function mapSupplierSummaryDto(dto: SupplierSummaryDto): SupplierSummary {
  return {
    id: dto.id,
    name: dto.name,
    gstin: dto.gstin ?? '',
    stateCode: dto.stateCode ?? '',
    stateName: dto.stateName ?? '',
    category: dto.category,
    status: mapApiSupplierStatus(dto.status),
    email: dto.email ?? '',
    totalInvoices: dto.totalInvoices,
    totalValue: toMoneyNumber(dto.totalValue),
    lastInvoiceDate: dto.lastInvoiceDate ?? '',
  };
}

export function mapWorkspaceSettingsDto(
  dto: WorkspaceSettingsDto,
  workspaceDetail: WorkspaceDetailDto | null,
  organizations: OrganizationSummary[]
): WorkspaceSettings {
  const parentOrg = organizations.find(
    (org) => org.id === workspaceDetail?.organizationId
  );

  return {
    workspaceName: workspaceDetail?.name ?? dto.legalEntityName,
    firmType: parentOrg?.firmType ?? 'Chartered Accountancy Practice',
    workspaceCode: workspaceDetail?.workspaceCode ?? '',
    legalEntityName: dto.legalEntityName,
    companyGstin: dto.companyGstin ?? '',
    companyPan: dto.companyPan ?? '',
    registeredAddress: dto.registeredAddress ?? '',
    requireHumanReview: true,
    enableDuplicateWarnings: dto.enableDuplicateWarnings,
    autoFlagTaxMismatch: dto.autoFlagTaxMismatch,
    currency: 'INR',
    financialYear: 'April - March',
    dateFormat: 'DD/MM/YYYY',
    taxRegime: 'India GST (CGST / SGST / IGST)',
    notifyFlaggedInvoices: dto.notifyFlaggedInvoices,
    notifyDailyDigest: dto.notifyDailyDigest,
    notifyDuplicateAlerts: dto.notifyDuplicateAlerts,
    roundingTolerance: toMoneyNumber(dto.roundingTolerance),
    defaultCurrency: dto.defaultCurrency,
    updatedAt: dto.updatedAt,
  };
}

export function mapMonthlyTrendDto(
  dto: MonthlyTrendResponseDto
): HistoricalMonthStat[] {
  return dto.buckets.map((b) => ({
    monthKey: b.monthKey,
    label: b.label,
    totalCount: b.totalCount,
    verifiedCount: b.verifiedCount,
    pendingCount: b.pendingCount,
    flaggedCount: b.flaggedCount,
    totalValue: toMoneyNumber(b.totalValue),
    totalTaxableValue: toMoneyNumber(b.totalTaxableValue),
    totalGst: toMoneyNumber(b.totalGst),
  }));
}

export function mapAuditEventToActivity(ev: ApiAuditEvent): ActivityEvent {
  const formattedTime = new Date(ev.createdAt).toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
  return {
    id: ev.id,
    timestamp: formattedTime,
    actor: ev.actorDisplayName,
    action: ev.summary,
    invoiceId: ev.entityType === 'invoice' && ev.entityId ? ev.entityId : undefined,
    tone: ev.tone,
  };
}
