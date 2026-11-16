import type {
  Invoice,
  InvoiceFieldKey,
  InvoiceFieldMeta,
  InvoiceStatus,
  Supplier,
  SupplierSummary,
} from '../types/domain';
import { formatINR, getTotalTax } from './formatters';

export type InvoiceSortField =
  | 'invoiceNumber'
  | 'supplierName'
  | 'invoiceDate'
  | 'totalAmount'
  | 'taxAmount'
  | 'status'
  | 'uploadDate';

export type SortDirection = 'asc' | 'desc';

export interface InvoiceFilterCriteria {
  search: string;
  status: 'All' | InvoiceStatus;
  taxType: 'All' | 'Intra-State (CGST+SGST)' | 'Inter-State (IGST)';
  supplierId?: string;
  supplierName?: string;
}

export function normalizeSupplierName(name: string): string {
  return name.trim().replace(/\s+/g, ' ').toLowerCase();
}

export function computeArithmeticCheck(invoice: {
  taxableAmount: number;
  cgst: number;
  sgst: number;
  igst: number;
  totalAmount: number;
}): { expectedTotal: number; difference: number; isBalanced: boolean } {
  const expectedTotal =
    Number(invoice.taxableAmount) +
    Number(invoice.cgst) +
    Number(invoice.sgst) +
    Number(invoice.igst);
  const difference = Number((Number(invoice.totalAmount) - expectedTotal).toFixed(2));
  return {
    expectedTotal,
    difference,
    isBalanced: Math.abs(difference) < 0.01,
  };
}

export function detectDuplicateWarning(
  candidate: Pick<
    Invoice,
    'id' | 'invoiceNumber' | 'supplierName' | 'totalAmount' | 'duplicateWarning'
  >,
  allInvoices: Invoice[]
): string | undefined {
  if (candidate.duplicateWarning) {
    return candidate.duplicateWarning;
  }

  const normalizedNumber = candidate.invoiceNumber.trim().toLowerCase();
  const normalizedSupplier = normalizeSupplierName(candidate.supplierName);

  for (const other of allInvoices) {
    if (other.id === candidate.id) continue;
    const sameSupplier =
      normalizeSupplierName(other.supplierName) === normalizedSupplier;
    if (!sameSupplier) continue;

    if (
      normalizedNumber &&
      other.invoiceNumber.trim().toLowerCase() === normalizedNumber
    ) {
      return `Potential duplicate invoice number: ${candidate.invoiceNumber} already exists for ${candidate.supplierName}.`;
    }

    if (
      candidate.totalAmount > 0 &&
      Math.abs(other.totalAmount - candidate.totalAmount) < 0.01
    ) {
      return `Similar total (${formatINR(candidate.totalAmount)}) recorded on ${other.invoiceNumber}. Confirm this is not a duplicate.`;
    }
  }

  return undefined;
}

export function filterAndSortInvoices(
  invoices: Invoice[],
  criteria: InvoiceFilterCriteria,
  sortField: InvoiceSortField,
  sortDirection: SortDirection
): Invoice[] {
  const query = criteria.search.trim().toLowerCase();
  const targetNormalizedSupplier = criteria.supplierName
    ? normalizeSupplierName(criteria.supplierName)
    : undefined;

  const filtered = invoices.filter((inv) => {
    if (criteria.status !== 'All' && inv.status !== criteria.status) {
      return false;
    }

    if (criteria.supplierId || targetNormalizedSupplier) {
      const matchesId = criteria.supplierId
        ? inv.supplierId === criteria.supplierId
        : false;
      const matchesName = targetNormalizedSupplier
        ? normalizeSupplierName(inv.supplierName) === targetNormalizedSupplier
        : false;
      if (!matchesId && !matchesName) {
        return false;
      }
    }

    if (criteria.taxType === 'Intra-State (CGST+SGST)' && inv.cgst + inv.sgst === 0) {
      return false;
    }

    if (criteria.taxType === 'Inter-State (IGST)' && inv.igst === 0) {
      return false;
    }

    if (query) {
      const haystack = `${inv.invoiceNumber} ${inv.supplierName} ${inv.supplierGstin}`.toLowerCase();
      if (!haystack.includes(query)) {
        return false;
      }
    }

    return true;
  });

  const factor = sortDirection === 'asc' ? 1 : -1;

  return [...filtered].sort((a, b) => {
    switch (sortField) {
      case 'totalAmount':
        return (a.totalAmount - b.totalAmount) * factor;
      case 'taxAmount':
        return (getTotalTax(a) - getTotalTax(b)) * factor;
      case 'invoiceNumber':
        return a.invoiceNumber.localeCompare(b.invoiceNumber) * factor;
      case 'supplierName':
        return a.supplierName.localeCompare(b.supplierName) * factor;
      case 'status':
        return a.status.localeCompare(b.status) * factor;
      case 'uploadDate':
        return a.uploadDate.localeCompare(b.uploadDate) * factor;
      case 'invoiceDate':
      default:
        return a.invoiceDate.localeCompare(b.invoiceDate) * factor;
    }
  });
}

export function buildSupplierSummaries(
  suppliers: Supplier[],
  invoices: Invoice[]
): SupplierSummary[] {
  return suppliers.map((sup) => {
    const normalizedSupName = normalizeSupplierName(sup.name);
    const supInvoices = invoices.filter(
      (inv) =>
        inv.supplierId === sup.id ||
        normalizeSupplierName(inv.supplierName) === normalizedSupName
    );
    const totalValue = supInvoices.reduce((sum, inv) => sum + inv.totalAmount, 0);
    const sortedDates = supInvoices
      .map((inv) => inv.invoiceDate)
      .sort((a, b) => b.localeCompare(a));

    return {
      ...sup,
      totalInvoices: supInvoices.length,
      totalValue,
      lastInvoiceDate: sortedDates[0] ?? '',
    };
  });
}

export function createDemoUploadedInvoice(params: {
  file: File;
  previewUrl: string;
  supplierName: string;
  invoiceNumber: string;
  suppliers?: Supplier[];
}): Invoice {
  const today = new Date().toISOString().slice(0, 10);
  const id = `inv-local-${Date.now()}`;
  const cleanNumber =
    params.invoiceNumber.trim() || `DEMO-${String(Date.now()).slice(-4)}`;
  const cleanSupplier =
    params.supplierName.trim() || 'Unassigned Supplier (Manual Entry Required)';

  const matchedSupplier = params.suppliers?.find(
    (sup) => normalizeSupplierName(sup.name) === normalizeSupplierName(cleanSupplier)
  );

  const fieldKeys: InvoiceFieldKey[] = [
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

  const fieldMeta = fieldKeys.reduce((acc, key) => {
    acc[key] = {
      status: 'Needs Review',
      evidenceNote:
        'Frontend Prototype: Local file staged without OCR/AI extraction. Enter and verify manually.',
    };
    return acc;
  }, {} as Record<InvoiceFieldKey, InvoiceFieldMeta>);

  return {
    id,
    invoiceNumber: cleanNumber,
    supplierId: matchedSupplier?.id ?? 'sup-local',
    supplierName: matchedSupplier?.name ?? cleanSupplier,
    supplierGstin: matchedSupplier?.gstin ?? 'PENDING-ENTRY',
    invoiceDate: today,
    uploadDate: today,
    taxableAmount: 0,
    cgst: 0,
    sgst: 0,
    igst: 0,
    totalAmount: 0,
    status: 'Pending Review',
    reviewerNote:
      'Locally staged document in Task 001 prototype. No automatic extraction has been run; please enter and verify accounting fields.',
    documentFileName: params.file.name,
    documentPageCount: 1,
    localPreviewUrl: params.previewUrl,
    localPreviewMimeType: params.file.type,
    isLocalUpload: true,
    lineItems: [],
    fieldMeta,
  };
}

export const PREDEFINED_FLAG_REASONS = [
  'Tax / total arithmetic mismatch',
  'Duplicate invoice suspicion',
  'Supplier GSTIN invalid or pending verification',
  'HSN / SAC code or GST rate mismatch',
  'Missing supporting PO / GRN reference',
] as const;

export const CUSTOM_FLAG_OPTION = '__CUSTOM__';

export function resolveFlagReason(params: {
  selectedReason: string;
  customReason: string;
}): { ok: true; reason: string } | { ok: false; error: string } {
  const trimmedCustom = params.customReason.trim();
  const isCustomMode = params.selectedReason === CUSTOM_FLAG_OPTION;

  if (isCustomMode) {
    if (!trimmedCustom) {
      return {
        ok: false,
        error: 'Enter a custom flag reason (cannot be empty or whitespace only).',
      };
    }
    return { ok: true, reason: trimmedCustom };
  }

  if (params.customReason.length > 0 && !trimmedCustom) {
    return {
      ok: false,
      error: 'Additional custom note cannot contain only whitespace.',
    };
  }

  const baseReason = params.selectedReason.trim();
  if (!baseReason) {
    return {
      ok: false,
      error: 'Select a flag reason or enter a custom reason.',
    };
  }

  if (trimmedCustom) {
    return { ok: true, reason: `${baseReason} — ${trimmedCustom}` };
  }

  return { ok: true, reason: baseReason };
}

const EDITABLE_FIELD_KEYS: InvoiceFieldKey[] = [
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

export function hasUnsavedInvoiceChanges(
  original: Invoice | undefined,
  draft: Invoice | undefined
): boolean {
  if (!original || !draft) return false;
  if (original.id !== draft.id) return false;

  if (
    original.supplierName !== draft.supplierName ||
    original.supplierGstin !== draft.supplierGstin ||
    original.invoiceNumber !== draft.invoiceNumber ||
    original.invoiceDate !== draft.invoiceDate ||
    original.taxableAmount !== draft.taxableAmount ||
    original.cgst !== draft.cgst ||
    original.sgst !== draft.sgst ||
    original.igst !== draft.igst ||
    original.totalAmount !== draft.totalAmount ||
    original.reviewerNote !== draft.reviewerNote ||
    (original.flagReason ?? '') !== (draft.flagReason ?? '')
  ) {
    return true;
  }

  for (const key of EDITABLE_FIELD_KEYS) {
    const origMeta = original.fieldMeta[key];
    const draftMeta = draft.fieldMeta[key];
    if (
      origMeta.status !== draftMeta.status ||
      origMeta.evidenceNote !== draftMeta.evidenceNote
    ) {
      return true;
    }
  }

  return false;
}

export function removeLocalStagedInvoice(
  invoices: Invoice[],
  invoiceId: string
): { updated: Invoice[]; removed: Invoice | null } {
  const target = invoices.find((inv) => inv.id === invoiceId);
  if (!target || !target.isLocalUpload) {
    return { updated: invoices, removed: null };
  }

  return {
    updated: invoices.filter((inv) => inv.id !== invoiceId),
    removed: target,
  };
}

