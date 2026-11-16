import { Building2, ExternalLink, Search } from 'lucide-react';
import { useMemo, useState } from 'react';
import { StatusBadge } from '../components/common/Badge';
import { Card } from '../components/common/Card';
import { EmptyState } from '../components/common/EmptyState';
import { formatDateIN, formatINR } from '../services/formatters';
import { buildSupplierSummaries } from '../services/invoiceService';
import { useWorkspace } from '../state/WorkspaceContext';
import type { SupplierStatus } from '../types/domain';

export function SuppliersPage() {
  const { suppliers, invoices, navigate } = useWorkspace();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'All' | SupplierStatus>('All');

  const summaries = useMemo(
    () => buildSupplierSummaries(suppliers, invoices),
    [suppliers, invoices]
  );

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return summaries.filter((sup) => {
      if (statusFilter !== 'All' && sup.status !== statusFilter) return false;
      if (q) {
        const hay = `${sup.name} ${sup.gstin} ${sup.category} ${sup.stateName}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [summaries, search, statusFilter]);

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">Suppliers Directory</h2>
        <p className="text-xs text-slate-500">
          Fictional sample vendor master with GSTIN placeholders and aggregated invoice
          totals.
        </p>
      </div>

      <Card>
        <div className="flex flex-col gap-3 border-b border-slate-100 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative max-w-md flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search supplier name, GSTIN, state, or category..."
              aria-label="Search suppliers"
              className="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 pl-9 pr-3 text-xs text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/15"
            />
          </div>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as 'All' | SupplierStatus)}
            aria-label="Filter by supplier status"
            className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 focus:border-indigo-500 focus:outline-none"
          >
            <option value="All">All Supplier Statuses</option>
            <option value="Verified">Verified</option>
            <option value="Needs Verification">Needs Verification</option>
            <option value="Flagged">Flagged</option>
          </select>
        </div>

        {filtered.length === 0 ? (
          <EmptyState
            icon={<Building2 className="h-5 w-5" />}
            title="No matching suppliers"
            description="No sample suppliers matched your search or status filter."
            action={
              <button
                type="button"
                onClick={() => {
                  setSearch('');
                  setStatusFilter('All');
                }}
                className="rounded-lg border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                Reset Filters
              </button>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/70 text-slate-500">
                  <th className="px-5 py-3 font-medium">Supplier Name</th>
                  <th className="px-5 py-3 font-medium">GSTIN (Placeholder)</th>
                  <th className="px-5 py-3 font-medium">State</th>
                  <th className="px-5 py-3 text-right font-medium">Total Invoices</th>
                  <th className="px-5 py-3 text-right font-medium">
                    Total Invoice Value
                  </th>
                  <th className="px-5 py-3 font-medium">Last Invoice Date</th>
                  <th className="px-5 py-3 font-medium">Supplier Status</th>
                  <th className="px-5 py-3 text-right font-medium">Invoices</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filtered.map((sup) => (
                  <tr key={sup.id} className="hover:bg-slate-50/70">
                    <td className="px-5 py-3.5">
                      <p className="font-semibold text-slate-900">{sup.name}</p>
                      <p className="text-[11px] text-slate-500">{sup.category}</p>
                    </td>
                    <td className="px-5 py-3.5 font-mono text-slate-700">
                      {sup.gstin}
                    </td>
                    <td className="px-5 py-3.5 text-slate-600">
                      {sup.stateCode} · {sup.stateName}
                    </td>
                    <td className="px-5 py-3.5 text-right font-mono font-medium tabular-nums text-slate-900">
                      {sup.totalInvoices}
                    </td>
                    <td className="px-5 py-3.5 text-right font-mono font-semibold tabular-nums text-slate-900">
                      {formatINR(sup.totalValue)}
                    </td>
                    <td className="px-5 py-3.5 font-mono text-slate-600 tabular-nums whitespace-nowrap">
                      {sup.lastInvoiceDate ? formatDateIN(sup.lastInvoiceDate) : '—'}
                    </td>
                    <td className="px-5 py-3.5">
                      <StatusBadge status={sup.status} />
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <button
                        type="button"
                        onClick={() => navigate('invoices', { supplierFilterId: sup.id })}
                        className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:border-indigo-300 hover:text-indigo-700 whitespace-nowrap"
                      >
                        View
                        <ExternalLink className="h-3 w-3" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
