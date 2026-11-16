import {
  ArrowDownUp,
  Eye,
  FileText,
  Filter,
  Search,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import { StatusBadge } from '../components/common/Badge';
import { Card } from '../components/common/Card';
import { ConfirmDialog } from '../components/common/ConfirmDialog';
import { EmptyState } from '../components/common/EmptyState';
import { UploadInvoiceModal } from '../components/invoices/UploadInvoiceModal';
import { formatDateIN, formatINR, getTotalTax } from '../services/formatters';
import {
  filterAndSortInvoices,
  type InvoiceSortField,
  type SortDirection,
} from '../services/invoiceService';
import { useWorkspace } from '../state/WorkspaceContext';
import type { Invoice, InvoiceStatus } from '../types/domain';

export function InvoicesPage() {
  const {
    invoices,
    suppliers,
    supplierFilterId,
    clearSupplierFilter,
    selectInvoiceForReview,
    deleteLocalInvoice,
  } = useWorkspace();

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'All' | InvoiceStatus>('All');
  const [taxTypeFilter, setTaxTypeFilter] = useState<
    'All' | 'Intra-State (CGST+SGST)' | 'Inter-State (IGST)'
  >('All');
  const [sortField, setSortField] = useState<InvoiceSortField>('invoiceDate');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  const [uploadOpen, setUploadOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Invoice | null>(null);

  const activeSupplierName = supplierFilterId
    ? suppliers.find((s) => s.id === supplierFilterId)?.name
    : undefined;

  const filteredInvoices = useMemo(
    () =>
      filterAndSortInvoices(
        invoices,
        {
          search,
          status: statusFilter,
          taxType: taxTypeFilter,
          supplierId: supplierFilterId ?? undefined,
          supplierName: activeSupplierName,
        },
        sortField,
        sortDirection
      ),
    [
      invoices,
      search,
      statusFilter,
      taxTypeFilter,
      supplierFilterId,
      activeSupplierName,
      sortField,
      sortDirection,
    ]
  );

  const handleSort = (field: InvoiceSortField) => {
    if (sortField === field) {
      setSortDirection((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  const resetFilters = () => {
    setSearch('');
    setStatusFilter('All');
    setTaxTypeFilter('All');
    clearSupplierFilter();
  };

  const renderSortButton = (
    label: string,
    field: InvoiceSortField,
    alignRight = false
  ) => (
    <button
      type="button"
      onClick={() => handleSort(field)}
      className={`inline-flex items-center gap-1 font-medium hover:text-slate-900 whitespace-nowrap ${
        alignRight ? 'ml-auto' : ''
      } ${sortField === field ? 'text-indigo-700' : 'text-slate-500'}`}
    >
      <span>{label}</span>
      <ArrowDownUp className="h-3 w-3" />
    </button>
  );

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Supplier Invoices</h2>
          <p className="text-xs text-slate-500">
            Search, filter, sort, and stage sample supplier invoices for verification.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setUploadOpen(true)}
          className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white hover:bg-indigo-700 whitespace-nowrap shrink-0"
        >
          <Upload className="h-4 w-4" />
          Upload Invoice
        </button>
      </div>

      <Card>
        <div className="flex flex-col gap-3 border-b border-slate-100 p-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="relative w-full max-w-md flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by invoice number, supplier, or GSTIN..."
              aria-label="Search invoices"
              className="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 pl-9 pr-3 text-xs text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/15"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <div className="inline-flex items-center gap-1.5 text-xs text-slate-500">
              <Filter className="h-3.5 w-3.5" />
              <span>Filters:</span>
            </div>

            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as 'All' | InvoiceStatus)}
              aria-label="Filter by status"
              className="h-10 w-full min-w-0 rounded-lg border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 focus:border-indigo-500 focus:outline-none sm:w-auto"
            >
              <option value="All">All Statuses</option>
              <option value="Pending Review">Pending Review</option>
              <option value="Verified">Verified</option>
              <option value="Flagged">Flagged</option>
            </select>

            <select
              value={taxTypeFilter}
              onChange={(e) =>
                setTaxTypeFilter(
                  e.target.value as
                    | 'All'
                    | 'Intra-State (CGST+SGST)'
                    | 'Inter-State (IGST)'
                )
              }
              aria-label="Filter by GST tax type"
              className="h-10 w-full min-w-0 rounded-lg border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 focus:border-indigo-500 focus:outline-none sm:w-auto"
            >
              <option value="All">All GST Types</option>
              <option value="Intra-State (CGST+SGST)">Intra-State (CGST+SGST)</option>
              <option value="Inter-State (IGST)">Inter-State (IGST)</option>
            </select>

            {activeSupplierName && (
              <button
                type="button"
                onClick={clearSupplierFilter}
                aria-label="Clear supplier filter"
                className="inline-flex h-10 max-w-full items-center gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50 px-3 text-xs font-medium text-indigo-700 hover:bg-indigo-100"
              >
                <span className="truncate">Supplier: {activeSupplierName}</span>
                <X className="h-3.5 w-3.5 shrink-0" />
              </button>
            )}
          </div>
        </div>

        {filteredInvoices.length === 0 ? (
          <EmptyState
            icon={<FileText className="h-5 w-5" />}
            title="No invoices match your criteria"
            description="Adjust your search query or status filters, or upload a sample PDF/image invoice to test the staging workflow."
            action={
              <button
                type="button"
                onClick={resetFilters}
                className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                Reset Filters
              </button>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/70">
                  <th className="px-5 py-3">
                    {renderSortButton('Invoice No.', 'invoiceNumber')}
                  </th>
                  <th className="px-5 py-3">
                    {renderSortButton('Supplier Name', 'supplierName')}
                  </th>
                  <th className="px-5 py-3">
                    {renderSortButton('Invoice Date', 'invoiceDate')}
                  </th>
                  <th className="px-5 py-3 text-right">
                    {renderSortButton('Amount', 'totalAmount', true)}
                  </th>
                  <th className="px-5 py-3 text-right">
                    {renderSortButton('Tax Amount', 'taxAmount', true)}
                  </th>
                  <th className="px-5 py-3">{renderSortButton('Status', 'status')}</th>
                  <th className="px-5 py-3">
                    {renderSortButton('Upload Date', 'uploadDate')}
                  </th>
                  <th className="px-5 py-3 text-right font-medium text-slate-500">
                    Action
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredInvoices.map((inv) => {
                  const taxAmount = getTotalTax(inv);
                  return (
                    <tr
                      key={inv.id}
                      onClick={() => selectInvoiceForReview(inv.id)}
                      className="cursor-pointer transition-colors hover:bg-slate-50"
                    >
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-semibold text-slate-900 whitespace-nowrap">
                            {inv.invoiceNumber}
                          </span>
                          {inv.isLocalUpload && (
                            <span className="text-[11px] font-medium text-indigo-600">
                              · Local
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-5 py-3.5">
                        <p className="font-medium text-slate-900">{inv.supplierName}</p>
                        <p className="font-mono text-[11px] text-slate-400">
                          {inv.supplierGstin}
                        </p>
                      </td>
                      <td className="px-5 py-3.5 font-mono text-slate-600 tabular-nums whitespace-nowrap">
                        {formatDateIN(inv.invoiceDate)}
                      </td>
                      <td className="px-5 py-3.5 text-right font-mono font-semibold text-slate-900 tabular-nums whitespace-nowrap">
                        {formatINR(inv.totalAmount)}
                      </td>
                      <td className="px-5 py-3.5 text-right font-mono text-slate-600 tabular-nums whitespace-nowrap">
                        {formatINR(taxAmount)}
                      </td>
                      <td className="px-5 py-3.5">
                        <StatusBadge status={inv.status} />
                        {inv.status === 'Flagged' && inv.flagReason && (
                          <p
                            title={inv.flagReason}
                            className="mt-1 max-w-[220px] truncate text-[11px] text-rose-700"
                          >
                            {inv.flagReason}
                          </p>
                        )}
                      </td>
                      <td className="px-5 py-3.5 font-mono text-slate-500 tabular-nums whitespace-nowrap">
                        {formatDateIN(inv.uploadDate)}
                      </td>
                      <td className="px-5 py-3.5 text-right">
                        <div className="inline-flex items-center justify-end gap-2">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              selectInvoiceForReview(inv.id);
                            }}
                            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:border-indigo-300 hover:text-indigo-700 whitespace-nowrap"
                          >
                            <Eye className="h-3.5 w-3.5" />
                            Review
                          </button>
                          {inv.isLocalUpload && (
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                setPendingDelete(inv);
                              }}
                              aria-label={`Delete locally staged invoice ${inv.invoiceNumber}`}
                              title="Delete locally staged demo invoice"
                              className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-rose-600 hover:border-rose-200 hover:bg-rose-50"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 px-5 py-3 text-xs text-slate-500">
          <span>
            Showing{' '}
            <strong className="font-mono text-slate-700 tabular-nums">
              {filteredInvoices.length}
            </strong>{' '}
            of{' '}
            <strong className="font-mono text-slate-700 tabular-nums">
              {invoices.length}
            </strong>{' '}
            sample invoices
          </span>
          <span>Click any row to open the Review Centre</span>
        </div>
      </Card>

      <UploadInvoiceModal open={uploadOpen} onClose={() => setUploadOpen(false)} />

      <ConfirmDialog
        open={pendingDelete !== null}
        tone="danger"
        title="Delete Locally Staged Demo Invoice?"
        description={
          pendingDelete ? (
            <p>
              Remove locally staged invoice{' '}
              <span className="font-mono font-semibold text-slate-900">
                {pendingDelete.invoiceNumber}
              </span>{' '}
              ({pendingDelete.documentFileName}) from your browser workspace and
              clean up its temporary preview URL? No server document is deleted.
            </p>
          ) : null
        }
        cancelLabel="Keep Invoice"
        confirmLabel="Delete Local Invoice"
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => {
          if (pendingDelete) {
            deleteLocalInvoice(pendingDelete.id);
          }
          setPendingDelete(null);
        }}
      />
    </div>
  );
}
