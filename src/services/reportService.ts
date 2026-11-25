import type { HistoricalMonthStat, Invoice } from '../types/domain';
import { getTotalTax } from './formatters';

export interface ReportMetrics {
  totalInvoices: number;
  verifiedCount: number;
  pendingCount: number;
  flaggedCount: number;
  verificationRatePercent: number;
  totalInvoiceValue: number;
  totalTaxableValue: number;
  totalCgst: number;
  totalSgst: number;
  totalIgst: number;
  totalGst: number;
  verifiedValue: number;
  pendingValue: number;
  flaggedValue: number;
}

export function computeReportMetrics(invoices: Invoice[]): ReportMetrics {
  const totalInvoices = invoices.length;
  const verified = invoices.filter((i) => i.status === 'Verified');
  const pending = invoices.filter((i) => i.status === 'Pending Review');
  const flagged = invoices.filter((i) => i.status === 'Flagged');

  const totalInvoiceValue = invoices.reduce((sum, i) => sum + i.totalAmount, 0);
  const totalTaxableValue = invoices.reduce((sum, i) => sum + i.taxableAmount, 0);
  const totalCgst = invoices.reduce((sum, i) => sum + i.cgst, 0);
  const totalSgst = invoices.reduce((sum, i) => sum + i.sgst, 0);
  const totalIgst = invoices.reduce((sum, i) => sum + i.igst, 0);

  return {
    totalInvoices,
    verifiedCount: verified.length,
    pendingCount: pending.length,
    flaggedCount: flagged.length,
    verificationRatePercent:
      totalInvoices > 0 ? Math.round((verified.length / totalInvoices) * 100) : 0,
    totalInvoiceValue,
    totalTaxableValue,
    totalCgst,
    totalSgst,
    totalIgst,
    totalGst: totalCgst + totalSgst + totalIgst,
    verifiedValue: verified.reduce((sum, i) => sum + i.totalAmount, 0),
    pendingValue: pending.reduce((sum, i) => sum + i.totalAmount, 0),
    flaggedValue: flagged.reduce((sum, i) => sum + i.totalAmount, 0),
  };
}

const SHORT_MONTH_NAMES = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
] as const;

export interface ParsedYearMonth {
  year: number;
  month: number;
  monthKey: string;
}

export function parseIsoYearMonth(isoDate: string): ParsedYearMonth | null {
  if (typeof isoDate !== 'string') return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate.trim());
  if (!match) return null;

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);

  if (year < 1970 || year > 2100 || month < 1 || month > 12 || day < 1 || day > 31) {
    return null;
  }

  const utc = new Date(Date.UTC(year, month - 1, day));
  if (
    utc.getUTCFullYear() !== year ||
    utc.getUTCMonth() !== month - 1 ||
    utc.getUTCDate() !== day
  ) {
    return null;
  }

  return {
    year,
    month,
    monthKey: `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}`,
  };
}

function formatMonthLabel(year: number, month: number): string {
  const shortYear = String(year).slice(-2);
  return `${SHORT_MONTH_NAMES[month - 1]} ${shortYear}`;
}

function toMonthIndex(year: number, month: number): number {
  return year * 12 + (month - 1);
}

function fromMonthIndex(index: number): { year: number; month: number; monthKey: string } {
  const year = Math.floor(index / 12);
  const month = (index % 12) + 1;
  return {
    year,
    month,
    monthKey: `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}`,
  };
}

export type TrendWindowOption = number | 'all';

export function buildMonthlyTrendStats(
  invoices: Invoice[],
  options: { windowMonths?: TrendWindowOption } = {}
): HistoricalMonthStat[] {
  const buckets = new Map<string, Invoice[]>();
  let minIndex = Infinity;
  let maxIndex = -Infinity;

  for (const inv of invoices) {
    const parsed = parseIsoYearMonth(inv.invoiceDate);
    if (!parsed) continue;
    const idx = toMonthIndex(parsed.year, parsed.month);
    if (idx < minIndex) minIndex = idx;
    if (idx > maxIndex) maxIndex = idx;

    const list = buckets.get(parsed.monthKey);
    if (list) {
      list.push(inv);
    } else {
      buckets.set(parsed.monthKey, [inv]);
    }
  }

  if (buckets.size === 0 || !Number.isFinite(maxIndex)) {
    return [];
  }

  const windowOption = options.windowMonths ?? 6;
  const startIndex =
    windowOption === 'all'
      ? minIndex
      : maxIndex - Math.max(1, Math.floor(windowOption)) + 1;

  const stats: HistoricalMonthStat[] = [];
  for (let idx = startIndex; idx <= maxIndex; idx += 1) {
    const { year, month, monthKey } = fromMonthIndex(idx);
    const monthInvoices = buckets.get(monthKey) ?? [];
    stats.push({
      monthKey,
      label: formatMonthLabel(year, month),
      totalCount: monthInvoices.length,
      verifiedCount: monthInvoices.filter((i) => i.status === 'Verified').length,
      pendingCount: monthInvoices.filter((i) => i.status === 'Pending Review').length,
      flaggedCount: monthInvoices.filter((i) => i.status === 'Flagged').length,
      totalValue: monthInvoices.reduce((sum, i) => sum + i.totalAmount, 0),
    });
  }

  return stats;
}

const FORMULA_PREFIX_PATTERN = /^[=+\-@\t\r\n]|^[\s\u0000-\u001f]+[=+\-@]/;

export function sanitizeCsvCell(value: string | number): string {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? String(value) : '0';
  }

  let str = String(value).replace(/\u0000/g, '');
  if (FORMULA_PREFIX_PATTERN.test(str)) {
    str = `'${str}`;
  }

  if (
    str.includes(',') ||
    str.includes('"') ||
    str.includes('\n') ||
    str.includes('\r')
  ) {
    return `"${str.replace(/"/g, '""')}"`;
  }

  return str;
}

function formatCsvAmount(amount: number): string {
  return Number.isFinite(amount) ? amount.toFixed(2) : '0.00';
}

export function buildInvoicesCsv(invoices: Invoice[], workspaceName: string): string {
  const headers = [
    'Workspace',
    'Invoice Number',
    'Supplier Name',
    'Supplier GSTIN',
    'Invoice Date',
    'Upload Date',
    'Taxable Amount (INR)',
    'CGST (INR)',
    'SGST (INR)',
    'IGST (INR)',
    'Total GST (INR)',
    'Total Amount (INR)',
    'Status',
    'Reviewer Note',
  ];

  const rows = invoices.map((inv) => [
    sanitizeCsvCell(workspaceName),
    sanitizeCsvCell(inv.invoiceNumber),
    sanitizeCsvCell(inv.supplierName),
    sanitizeCsvCell(inv.supplierGstin),
    sanitizeCsvCell(inv.invoiceDate),
    sanitizeCsvCell(inv.uploadDate),
    formatCsvAmount(inv.taxableAmount),
    formatCsvAmount(inv.cgst),
    formatCsvAmount(inv.sgst),
    formatCsvAmount(inv.igst),
    formatCsvAmount(getTotalTax(inv)),
    formatCsvAmount(inv.totalAmount),
    sanitizeCsvCell(inv.status),
    sanitizeCsvCell(inv.reviewerNote),
  ]);

  return [
    headers.map((h) => sanitizeCsvCell(h)).join(','),
    ...rows.map((row) => row.join(',')),
  ].join('\n');
}

export function exportInvoicesToCsv(invoices: Invoice[], workspaceName: string): void {
  const csvContent = buildInvoicesCsv(invoices, workspaceName);
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `norus-billwise-report-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
