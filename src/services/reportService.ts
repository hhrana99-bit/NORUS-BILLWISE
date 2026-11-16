import { HISTORICAL_MONTH_BASELINES } from '../data/mockData';
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

export function buildMonthlyTrendStats(invoices: Invoice[]): HistoricalMonthStat[] {
  const aggregateMonth = (monthKey: string, label: string): HistoricalMonthStat => {
    const monthInvoices = invoices.filter((inv) => inv.invoiceDate.startsWith(monthKey));
    return {
      monthKey,
      label,
      totalCount: monthInvoices.length,
      verifiedCount: monthInvoices.filter((i) => i.status === 'Verified').length,
      pendingCount: monthInvoices.filter((i) => i.status === 'Pending Review').length,
      flaggedCount: monthInvoices.filter((i) => i.status === 'Flagged').length,
      totalValue: monthInvoices.reduce((sum, i) => sum + i.totalAmount, 0),
    };
  };

  return [
    ...HISTORICAL_MONTH_BASELINES,
    aggregateMonth('2026-10', 'Oct 26'),
    aggregateMonth('2026-11', 'Nov 26'),
  ];
}

function escapeCsvCell(value: string | number): string {
  const str = String(value);
  if (str.includes(',') || str.includes('"') || str.includes('\n')) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

export function exportInvoicesToCsv(invoices: Invoice[], workspaceName: string): void {
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
    workspaceName,
    inv.invoiceNumber,
    inv.supplierName,
    inv.supplierGstin,
    inv.invoiceDate,
    inv.uploadDate,
    inv.taxableAmount.toFixed(2),
    inv.cgst.toFixed(2),
    inv.sgst.toFixed(2),
    inv.igst.toFixed(2),
    getTotalTax(inv).toFixed(2),
    inv.totalAmount.toFixed(2),
    inv.status,
    inv.reviewerNote,
  ]);

  const csvContent = [
    headers.map(escapeCsvCell).join(','),
    ...rows.map((row) => row.map(escapeCsvCell).join(',')),
  ].join('\n');

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
