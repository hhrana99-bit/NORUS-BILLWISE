import {
  Building2,
  ExternalLink,
  Lock,
  Pencil,
  Plus,
  Search,
  X,
} from 'lucide-react';
import { useMemo, useState, type FormEvent } from 'react';
import { StatusBadge } from '../components/common/Badge';
import { Card } from '../components/common/Card';
import { EmptyState } from '../components/common/EmptyState';
import { DEMO_MODE_DISABLED_ACTION_MESSAGE } from '../config/demoMode';
import { formatApiErrorMessage } from '../services/apiClient';
import { mapUiSupplierStatusToApi } from '../services/apiMappers';
import { formatDateIN, formatINR } from '../services/formatters';
import { useWorkspace } from '../state/WorkspaceContext';
import type { SupplierStatus, SupplierSummary } from '../types/domain';

export function SuppliersPage() {
  const {
    isDemoMode,
    suppliers,
    activeWorkspaceRole,
    navigate,
    createSupplierAction,
    updateSupplierAction,
    localUiPrefs,
  } = useWorkspace();

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'All' | SupplierStatus>(
    'All'
  );
  const [modalOpen, setModalOpen] = useState(false);
  const [editingSupplier, setEditingSupplier] =
    useState<SupplierSummary | null>(null);

  const [name, setName] = useState('');
  const [gstin, setGstin] = useState('');
  const [category, setCategory] = useState('General Vendor');
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<SupplierStatus>('Needs Verification');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const canManageSuppliers =
    !isDemoMode &&
    (activeWorkspaceRole === 'WORKSPACE_ADMIN' ||
      activeWorkspaceRole === 'REVIEWER');

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return suppliers.filter((sup) => {
      if (statusFilter !== 'All' && sup.status !== statusFilter) return false;
      if (q) {
        const hay =
          `${sup.name} ${sup.gstin} ${sup.category} ${sup.stateName}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [suppliers, search, statusFilter]);

  const openCreateModal = () => {
    setEditingSupplier(null);
    setName('');
    setGstin('');
    setCategory('General Vendor');
    setEmail('');
    setStatus('Needs Verification');
    setFormError(null);
    setModalOpen(true);
  };

  const openEditModal = (sup: SupplierSummary) => {
    setEditingSupplier(sup);
    setName(sup.name);
    setGstin(sup.gstin);
    setCategory(sup.category);
    setEmail(sup.email);
    setStatus(sup.status);
    setFormError(null);
    setModalOpen(true);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (isDemoMode) return;
    if (!name.trim()) {
      setFormError('Supplier name is required.');
      return;
    }
    setFormError(null);
    setSubmitting(true);
    try {
      const payload = {
        name: name.trim(),
        gstin: gstin.trim() || null,
        category: category.trim() || 'General Vendor',
        email: email.trim() || null,
        status: mapUiSupplierStatusToApi(status),
      };
      if (editingSupplier) {
        await updateSupplierAction(editingSupplier.id, payload);
      } else {
        await createSupplierAction(payload);
      }
      setModalOpen(false);
    } catch (err) {
      setFormError(formatApiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  const cellPad = localUiPrefs.compactTables ? 'px-4 py-2' : 'px-5 py-3.5';

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">
            Suppliers Directory
          </h2>
          <p className="text-xs text-slate-500">
            Workspace vendor master with GSTIN records and server-aggregated
            invoice totals.
          </p>
        </div>
        {(canManageSuppliers || isDemoMode) && (
          <button
            type="button"
            disabled={isDemoMode}
            title={isDemoMode ? DEMO_MODE_DISABLED_ACTION_MESSAGE : undefined}
            onClick={openCreateModal}
            className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white hover:bg-indigo-700 whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Plus className="h-4 w-4" />
            Add Supplier
          </button>
        )}
      </div>

      {isDemoMode && (
        <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-100 px-4 py-2.5 text-xs text-slate-700">
          <Lock className="h-4 w-4 shrink-0 text-slate-500" />
          <span>
            <strong>Demo Mode (Sample Data):</strong> Browse and search sample
            suppliers or inspect their invoices. Adding or editing suppliers is
            unavailable in read-only demo mode.
          </span>
        </div>
      )}

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
            onChange={(e) =>
              setStatusFilter(e.target.value as 'All' | SupplierStatus)
            }
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
            description="No workspace suppliers matched your search or status filter."
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
                  <th className="px-5 py-3 font-medium">GSTIN</th>
                  <th className="px-5 py-3 font-medium">State</th>
                  <th className="px-5 py-3 text-right font-medium">
                    Total Invoices
                  </th>
                  <th className="px-5 py-3 text-right font-medium">
                    Total Invoice Value
                  </th>
                  <th className="px-5 py-3 font-medium">Last Invoice Date</th>
                  <th className="px-5 py-3 font-medium">Supplier Status</th>
                  <th className="px-5 py-3 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filtered.map((sup) => (
                  <tr key={sup.id} className="hover:bg-slate-50/70">
                    <td className={cellPad}>
                      <p className="font-semibold text-slate-900">{sup.name}</p>
                      <p className="text-[11px] text-slate-500">
                        {sup.category}
                      </p>
                    </td>
                    <td className={`${cellPad} font-mono text-slate-700`}>
                      {sup.gstin || '—'}
                    </td>
                    <td className={`${cellPad} text-slate-600`}>
                      {sup.stateCode || sup.stateName
                        ? `${sup.stateCode || '--'} · ${sup.stateName || 'India'}`
                        : '—'}
                    </td>
                    <td
                      className={`${cellPad} text-right font-mono font-medium tabular-nums text-slate-900`}
                    >
                      {sup.totalInvoices}
                    </td>
                    <td
                      className={`${cellPad} text-right font-mono font-semibold tabular-nums text-slate-900`}
                    >
                      {formatINR(sup.totalValue)}
                    </td>
                    <td
                      className={`${cellPad} font-mono text-slate-600 tabular-nums whitespace-nowrap`}
                    >
                      {sup.lastInvoiceDate
                        ? formatDateIN(sup.lastInvoiceDate)
                        : '—'}
                    </td>
                    <td className={cellPad}>
                      <StatusBadge status={sup.status} />
                    </td>
                    <td className={`${cellPad} text-right`}>
                      <div className="inline-flex items-center gap-2">
                        {canManageSuppliers && (
                          <button
                            type="button"
                            onClick={() => openEditModal(sup)}
                            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                          >
                            <Pencil className="h-3 w-3" />
                            Edit
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() =>
                            navigate('invoices', { supplierFilterId: sup.id })
                          }
                          className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:border-indigo-300 hover:text-indigo-700 whitespace-nowrap"
                        >
                          View
                          <ExternalLink className="h-3 w-3" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {modalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="supplier-modal-title"
        >
          <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
              <h3
                id="supplier-modal-title"
                className="text-sm font-semibold text-slate-900"
              >
                {editingSupplier ? 'Edit Supplier' : 'Add Supplier'}
              </h3>
              <button
                type="button"
                disabled={submitting}
                onClick={() => setModalOpen(false)}
                className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100"
                aria-label="Close modal"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <form onSubmit={handleSubmit} className="space-y-3 p-5 text-xs">
              <div>
                <label className="block font-medium text-slate-700">
                  Supplier Name *
                </label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="mt-1 h-9 w-full rounded-lg border border-slate-200 px-3"
                />
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <label className="block font-medium text-slate-700">
                    GSTIN
                  </label>
                  <input
                    type="text"
                    value={gstin}
                    onChange={(e) => setGstin(e.target.value)}
                    placeholder="27AABCA1234M1Z5"
                    className="mt-1 h-9 w-full rounded-lg border border-slate-200 px-3 font-mono"
                  />
                </div>
                <div>
                  <label className="block font-medium text-slate-700">
                    Status
                  </label>
                  <select
                    value={status}
                    onChange={(e) =>
                      setStatus(e.target.value as SupplierStatus)
                    }
                    className="mt-1 h-9 w-full rounded-lg border border-slate-200 px-2.5"
                  >
                    <option value="Verified">Verified</option>
                    <option value="Needs Verification">
                      Needs Verification
                    </option>
                    <option value="Flagged">Flagged</option>
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <label className="block font-medium text-slate-700">
                    Category
                  </label>
                  <input
                    type="text"
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    className="mt-1 h-9 w-full rounded-lg border border-slate-200 px-3"
                  />
                </div>
                <div>
                  <label className="block font-medium text-slate-700">
                    Contact Email
                  </label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="mt-1 h-9 w-full rounded-lg border border-slate-200 px-3"
                  />
                </div>
              </div>

              {formError && (
                <p className="font-medium text-rose-600" role="alert">
                  {formError}
                </p>
              )}

              <div className="flex justify-end gap-2 border-t border-slate-100 pt-3">
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => setModalOpen(false)}
                  className="h-9 rounded-lg border border-slate-200 px-4 font-semibold text-slate-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="h-9 rounded-lg bg-indigo-600 px-4 font-semibold text-white hover:bg-indigo-700 disabled:opacity-60"
                >
                  {submitting
                    ? 'Saving...'
                    : editingSupplier
                      ? 'Save Changes'
                      : 'Create Supplier'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
