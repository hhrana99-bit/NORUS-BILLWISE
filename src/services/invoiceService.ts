import type {
  Invoice,
  InvoiceFieldKey,
  InvoiceFieldMeta,
  InvoiceStatus,
  Supplier,
  SupplierSummary,
} from '../types/domain';
import { getTotalTax } from './formatters';

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

export function filterAndSortInvoices(
  invoices: Invoice[],
  criteria: InvoiceFilterCriteria,
  sortField: InvoiceSortField,
  sortDirection: SortDirection
): Invoice[] {
  const query = criteria.search.trim().toLowerCase();

  const filtered = invoices.filter((inv) => {
    if (criteria.status !== 'All' && inv.status !== criteria.status) {
      return false;
    }

    if (criteria.supplierId && inv.supplierId !== criteria.supplierId) {
      return false;
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
    const supInvoices = invoices.filter(
      (inv) =>
        inv.supplierId === sup.id ||
        inv.supplierName.toLowerCase() === sup.name.toLowerCase()
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
}): Invoice {
  const today = new Date().toISOString().slice(0, 10);
  const id = `inv-local-${Date.now()}`;
  const cleanNumber =
    params.invoiceNumber.trim() || `DEMO-${String(Date.now()).slice(-4)}`;
  const cleanSupplier =
    params.supplierName.trim() || 'Unassigned Supplier (Manual Entry Required)';

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
    supplierId: 'sup-local',
    supplierName: cleanSupplier,
    supplierGstin: 'PENDING-ENTRY',
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
