import {
  ArrowDownUp,
  ChevronLeft,
  ChevronRight,
  Eye,
  FileText,
  Filter,
  Lock,
  Plus,
  Search,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { StatusBadge } from '../components/common/Badge';
import { Card } from '../components/common/Card';
import { ConfirmDialog } from '../components/common/ConfirmDialog';
import { EmptyState } from '../components/common/EmptyState';
import { UploadInvoiceModal } from '../components/invoices/UploadInvoiceModal';
import { DEMO_MODE_DISABLED_ACTION_MESSAGE } from '../config/demoMode';
import { apiClient, formatApiErrorMessage } from '../services/apiClient';
import {
  mapInvoiceSummaryDto,
  mapUiInvoiceStatusToApi,
} from '../services/apiMappers';
import { listDemoInvoices } from '../services/demoDataService';
import { formatDateIN, formatINR, getTotalTax } from '../services/formatters';
import type {
  InvoiceSortField,
  SortDirection,
} from '../services/invoiceService';
import { useWorkspace } from '../state/WorkspaceContext';
import type { Invoice, InvoiceStatus } from '../types/domain';

const PAGE_SIZE = 20;

export function InvoicesPage() {
  const {
    isDemoMode,
    activeWorkspaceId,
    activeWorkspaceRole,
    suppliers,
    supplierFilterId,
    clearSupplierFilter,
    selectInvoiceForReview,
    createManualInvoice,
    deleteInvoiceAction,
    localUiPrefs,
  } = useWorkspace();

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'All' | InvoiceStatus>('All');
  const [taxTypeFilter, setTaxTypeFilter] = useState<
    'All' | 'Intra-State (CGST+SGST)' | 'Inter-State (IGST)'
  >('All');
  const [sortField, setSortField] = useState<InvoiceSortField>('invoiceDate');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  const [page, setPage] = useState(1);

  const [rows, setRows] = useState<Invoice[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [uploadOpen, setUploadOpen] = useState(false);
  const [manualModalOpen, setManualModalOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Invoice | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [manualSupplierName, setManualSupplierName] = useState('');
  const [manualSupplierGstin, setManualSupplierGstin] = useState('');
  const [manualInvoiceNumber, setManualInvoiceNumber] = useState('');
  const [manualInvoiceDate, setManualInvoiceDate] = useState('');
  const [manualTaxable, setManualTaxable] = useState('0.00');
  const [manualCgst, setManualCgst] = useState('0.00');
  const [manualSgst, setManualSgst] = useState('0.00');
  const [manualIgst, setManualIgst] = useState('0.00');
  const [manualTotal, setManualTotal] = useState('0.00');
  const [manualCreating, setManualCreating] = useState(false);
  const [manualError, setManualError] = useState<string | null>(null);

  const canCreateOrUpload =
    !isDemoMode &&
    (activeWorkspaceRole === 'WORKSPACE_ADMIN' ||
      activeWorkspaceRole === 'REVIEWER' ||
      activeWorkspaceRole === 'UPLOADER');
  const isWorkspaceAdmin =
    !isDemoMode && activeWorkspaceRole === 'WORKSPACE_ADMIN';

  const activeSupplierName = supplierFilterId
    ? suppliers.find((s) => s.id === supplierFilterId)?.name
    : undefined;

  const fetchInvoices = useCallback(
    async (signal?: AbortSignal) => {
      if (!activeWorkspaceId) return;
      if (isDemoMode) {
        const res = listDemoInvoices({
          search: search.trim() || undefined,
          status: statusFilter,
          taxType: taxTypeFilter,
          supplierId: supplierFilterId,
          sortBy: sortField,
          sortDir: sortDirection,
          page,
          pageSize: PAGE_SIZE,
        });
        setRows(res.items);
        setTotal(res.total);
        setLoadError(null);
        setLoading(false);
        return;
      }

      setLoading(true);
      setLoadError(null);
      try {
        const res = await apiClient.listInvoices(
          activeWorkspaceId,
          {
            search: search.trim() || undefined,
            status:
              statusFilter === 'All'
                ? undefined
                : mapUiInvoiceStatusToApi(statusFilter),
            taxType:
              taxTypeFilter === 'All'
                ? undefined
                : taxTypeFilter === 'Intra-State (CGST+SGST)'
                  ? 'INTRA_STATE'
                  : 'INTER_STATE',
            supplierId: supplierFilterId ?? undefined,
            sortBy: sortField,
            sortDir: sortDirection,
            page,
            pageSize: PAGE_SIZE,
          },
          signal
        );
        if (signal?.aborted) return;
        setRows(res.items.map(mapInvoiceSummaryDto));
        setTotal(res.total);
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return;
        setLoadError(formatApiErrorMessage(err));
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [
      activeWorkspaceId,
      isDemoMode,
      page,
      search,
      sortDirection,
      sortField,
      statusFilter,
      supplierFilterId,
      taxTypeFilter,
    ]
  );

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      void fetchInvoices(controller.signal);
    }, 150);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [fetchInvoices]);

  useEffect(() => {
    setPage(1);
  }, [search, statusFilter, taxTypeFilter, supplierFilterId]);

  const handleSort = (field: InvoiceSortField) => {
    if (sortField === field) {
      setSortDirection((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
    setPage(1);
  };

  const resetFilters = () => {
    setSearch('');
    setStatusFilter('All');
    setTaxTypeFilter('All');
    setPage(1);
    clearSupplierFilter();
  };

  const handleCreateManual = async (e: FormEvent) => {
    e.preventDefault();
    if (isDemoMode) return;
    setManualError(null);
    if (!manualInvoiceNumber.trim()) {
      setManualError('Invoice number is required.');
      return;
    }
    setManualCreating(true);
    try {
      const created = await createManualInvoice({
        supplierName: manualSupplierName.trim() || undefined,
        supplierGstin: manualSupplierGstin.trim() || undefined,
        invoiceNumber: manualInvoiceNumber.trim(),
        invoiceDate: manualInvoiceDate || undefined,
        taxableAmount: manualTaxable || '0.00',
        cgstAmount: manualCgst || '0.00',
        sgstAmount: manualSgst || '0.00',
        igstAmount: manualIgst || '0.00',
        totalAmount: manualTotal || '0.00',
      });
      setManualModalOpen(false);
      setManualSupplierName('');
      setManualSupplierGstin('');
      setManualInvoiceNumber('');
      setManualInvoiceDate('');
      selectInvoiceForReview(created.id);
    } catch (err) {
      setManualError(formatApiErrorMessage(err));
    } finally {
      setManualCreating(false);
    }
  };

  const handleDeleteConfirm = async () => {
    if (isDemoMode || !pendingDelete) return;
    setActionError(null);
    const targetId = pendingDelete.id;
    setPendingDelete(null);
    try {
      await deleteInvoiceAction(targetId, 'Deleted from Invoices register');
      await fetchInvoices();
    } catch (err) {
      setActionError(formatApiErrorMessage(err));
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const cellPad = localUiPrefs.compactTables ? 'px-4 py-2' : 'px-5 py-3.5';

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
          <h2 className="text-lg font-semibold text-slate-900">
            Supplier Invoices
          </h2>
          <p className="text-xs text-slate-500">
            Search, filter, sort, upload documents, or create manual accounting
            entries.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={!canCreateOrUpload}
            title={isDemoMode ? DEMO_MODE_DISABLED_ACTION_MESSAGE : undefined}
            onClick={() => {
              setManualError(null);
              setManualModalOpen(true);
            }}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Plus className="h-4 w-4" />
            New Manual Invoice
          </button>
          <button
            type="button"
            disabled={!canCreateOrUpload}
            title={isDemoMode ? DEMO_MODE_DISABLED_ACTION_MESSAGE : undefined}
            onClick={() => setUploadOpen(true)}
            className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white hover:bg-indigo-700 whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Upload className="h-4 w-4" />
            Upload Invoice
          </button>
        </div>
      </div>

      {isDemoMode && (
        <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-100 px-4 py-2.5 text-xs text-slate-700">
          <Lock className="h-4 w-4 shrink-0 text-slate-500" />
          <span>
            <strong>Demo Mode (Sample Data):</strong> Search, filter, sort, and
            inspect sample invoices below. Uploads, manual invoice creation, and
            deletions are unavailable in read-only demo mode.
          </span>
        </div>
      )}

      {(loadError || actionError) && (
        <div
          role="alert"
          className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-900"
        >
          {loadError || actionError}
        </div>
      )}

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
              onChange={(e) =>
                setStatusFilter(e.target.value as 'All' | InvoiceStatus)
              }
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
              <option value="Intra-State (CGST+SGST)">
                Intra-State (CGST+SGST)
              </option>
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

        {loading && rows.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-500">
            Loading workspace invoices...
          </div>
        ) : rows.length === 0 ? (
          <EmptyState
            icon={<FileText className="h-5 w-5" />}
            title="No invoices match your criteria"
            description="Adjust your search query or filters, or upload a PDF/image invoice."
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
                  <th className="px-5 py-3">
                    {renderSortButton('Status', 'status')}
                  </th>
                  <th className="px-5 py-3">
                    {renderSortButton('Upload Date', 'uploadDate')}
                  </th>
                  <th className="px-5 py-3 text-right font-medium text-slate-500">
                    Action
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((inv) => {
                  const taxAmount = getTotalTax(inv);
                  const canDelete =
                    isWorkspaceAdmin && inv.status !== 'Verified';
                  return (
                    <tr
                      key={inv.id}
                      onClick={() => selectInvoiceForReview(inv.id)}
                      className="cursor-pointer transition-colors hover:bg-slate-50"
                    >
                      <td className={cellPad}>
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-semibold text-slate-900 whitespace-nowrap">
                            {inv.invoiceNumber}
                          </span>
                          {(inv.openFlagCount ?? 0) > 0 && (
                            <span className="font-mono text-[11px] font-medium text-rose-600">
                              · {inv.openFlagCount} flag(s)
                            </span>
                          )}
                        </div>
                      </td>
                      <td className={cellPad}>
                        <p className="font-medium text-slate-900">
                          {inv.supplierName}
                        </p>
                        <p className="font-mono text-[11px] text-slate-400">
                          {inv.supplierGstin || 'GSTIN pending'}
                        </p>
                      </td>
                      <td
                        className={`${cellPad} font-mono text-slate-600 tabular-nums whitespace-nowrap`}
                      >
                        {inv.invoiceDate ? formatDateIN(inv.invoiceDate) : '—'}
                      </td>
                      <td
                        className={`${cellPad} text-right font-mono font-semibold text-slate-900 tabular-nums whitespace-nowrap`}
                      >
                        {formatINR(inv.totalAmount)}
                      </td>
                      <td
                        className={`${cellPad} text-right font-mono text-slate-600 tabular-nums whitespace-nowrap`}
                      >
                        {formatINR(taxAmount)}
                      </td>
                      <td className={cellPad}>
                        <StatusBadge status={inv.status} />
                        {inv.duplicateWarning && (
                          <p
                            title={inv.duplicateWarning}
                            className="mt-1 max-w-[200px] truncate text-[11px] text-amber-700"
                          >
                            {inv.duplicateWarning}
                          </p>
                        )}
                      </td>
                      <td
                        className={`${cellPad} font-mono text-slate-500 tabular-nums whitespace-nowrap`}
                      >
                        {formatDateIN(inv.uploadDate)}
                      </td>
                      <td className={`${cellPad} text-right`}>
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
                          {canDelete && (
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                setPendingDelete(inv);
                              }}
                              aria-label={`Soft-delete invoice ${inv.invoiceNumber}`}
                              title="Soft-delete unverified invoice"
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

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-5 py-3 text-xs text-slate-500">
          <span>
            Showing{' '}
            <strong className="font-mono text-slate-700 tabular-nums">
              {rows.length}
            </strong>{' '}
            of{' '}
            <strong className="font-mono text-slate-700 tabular-nums">
              {total}
            </strong>{' '}
            workspace invoices
          </span>

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              Prev
            </button>
            <span className="font-mono text-xs text-slate-700 tabular-nums">
              Page {page} / {totalPages}
            </span>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
            >
              Next
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </Card>

      <UploadInvoiceModal
        open={uploadOpen}
        onClose={() => {
          setUploadOpen(false);
          void fetchInvoices();
        }}
      />

      {manualModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-3 sm:p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="manual-invoice-title"
          onClick={(e) => {
            if (e.target === e.currentTarget && !manualCreating) {
              setManualModalOpen(false);
            }
          }}
        >
          <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-slate-200 bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
              <h2
                id="manual-invoice-title"
                className="text-sm font-semibold text-slate-900"
              >
                New Manual Supplier Invoice
              </h2>
              <button
                type="button"
                disabled={manualCreating}
                onClick={() => setManualModalOpen(false)}
                className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100"
                aria-label="Close modal"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <form onSubmit={handleCreateManual} className="space-y-4 p-5 text-xs">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <label className="block font-medium text-slate-700">
                    Invoice Number *
                  </label>
                  <input
                    type="text"
                    required
                    value={manualInvoiceNumber}
                    onChange={(e) => setManualInvoiceNumber(e.target.value)}
                    placeholder="INV/2026-27/101"
                    className="mt-1 h-9 w-full rounded-lg border border-slate-200 px-3 font-mono"
                  />
                </div>
                <div>
                  <label className="block font-medium text-slate-700">
                    Invoice Date
                  </label>
                  <input
                    type="date"
                    value={manualInvoiceDate}
                    onChange={(e) => setManualInvoiceDate(e.target.value)}
                    className="mt-1 h-9 w-full rounded-lg border border-slate-200 px-3"
                  />
                </div>
                <div>
                  <label className="block font-medium text-slate-700">
                    Supplier Name
                  </label>
                  <input
                    type="text"
                    value={manualSupplierName}
                    onChange={(e) => setManualSupplierName(e.target.value)}
                    placeholder="Supplier Legal Name"
                    className="mt-1 h-9 w-full rounded-lg border border-slate-200 px-3"
                  />
                </div>
                <div>
                  <label className="block font-medium text-slate-700">
                    Supplier GSTIN
                  </label>
                  <input
                    type="text"
                    value={manualSupplierGstin}
                    onChange={(e) => setManualSupplierGstin(e.target.value)}
                    placeholder="27AABCA1234M1Z5"
                    className="mt-1 h-9 w-full rounded-lg border border-slate-200 px-3 font-mono"
                  />
                </div>
                <div>
                  <label className="block font-medium text-slate-700">
                    Taxable Amount (INR)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={manualTaxable}
                    onChange={(e) => setManualTaxable(e.target.value)}
                    className="mt-1 h-9 w-full rounded-lg border border-slate-200 px-3 font-mono"
                  />
                </div>
                <div>
                  <label className="block font-medium text-slate-700">
                    CGST (INR)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={manualCgst}
                    onChange={(e) => setManualCgst(e.target.value)}
                    className="mt-1 h-9 w-full rounded-lg border border-slate-200 px-3 font-mono"
                  />
                </div>
                <div>
                  <label className="block font-medium text-slate-700">
                    SGST (INR)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={manualSgst}
                    onChange={(e) => setManualSgst(e.target.value)}
                    className="mt-1 h-9 w-full rounded-lg border border-slate-200 px-3 font-mono"
                  />
                </div>
                <div>
                  <label className="block font-medium text-slate-700">
                    IGST (INR)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={manualIgst}
                    onChange={(e) => setManualIgst(e.target.value)}
                    className="mt-1 h-9 w-full rounded-lg border border-slate-200 px-3 font-mono"
                  />
                </div>
                <div className="sm:col-span-2">
                  <label className="block font-medium text-slate-700">
                    Total Invoice Amount (INR)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={manualTotal}
                    onChange={(e) => setManualTotal(e.target.value)}
                    className="mt-1 h-9 w-full rounded-lg border border-slate-200 px-3 font-mono font-semibold"
                  />
                </div>
              </div>

              {manualError && (
                <p className="font-medium text-rose-600" role="alert">
                  {manualError}
                </p>
              )}

              <div className="flex justify-end gap-2 border-t border-slate-100 pt-3">
                <button
                  type="button"
                  disabled={manualCreating}
                  onClick={() => setManualModalOpen(false)}
                  className="h-9 rounded-lg border border-slate-200 px-4 font-semibold text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={manualCreating}
                  className="h-9 rounded-lg bg-indigo-600 px-4 font-semibold text-white hover:bg-indigo-700 disabled:opacity-60"
                >
                  {manualCreating ? 'Creating...' : 'Create Draft & Review'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        tone="danger"
        title="Soft-Delete Invoice?"
        description={
          pendingDelete ? (
            <p>
              Soft-delete invoice{' '}
              <span className="font-mono font-semibold text-slate-900">
                {pendingDelete.invoiceNumber}
              </span>{' '}
              from the active workspace ledger? Audit trail history is preserved.
            </p>
          ) : null
        }
        cancelLabel="Keep Invoice"
        confirmLabel="Soft-Delete Invoice"
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => void handleDeleteConfirm()}
      />
    </div>
  );
}
