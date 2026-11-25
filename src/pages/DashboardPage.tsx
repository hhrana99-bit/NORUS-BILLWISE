import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  FileText,
  ShieldCheck,
} from 'lucide-react';
import { StatusBadge } from '../components/common/Badge';
import { Card, CardHeader } from '../components/common/Card';
import { KpiCard } from '../components/common/KpiCard';
import { formatDateIN, formatINR, formatINRCompact } from '../services/formatters';
import { computeReportMetrics } from '../services/reportService';
import { useWorkspace } from '../state/WorkspaceContext';

function toNumber(val: string | number | undefined | null): number {
  if (val === null || val === undefined || val === '') return 0;
  const parsed = Number(val);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function DashboardPage() {
  const {
    activeWorkspace,
    invoices,
    suppliers,
    activities,
    reportSummary,
    workspaceLoading,
    reportsError,
    navigate,
    selectInvoiceForReview,
  } = useWorkspace();

  const fallbackMetrics = computeReportMetrics(invoices);

  const metrics = reportSummary
    ? {
        totalInvoices: reportSummary.totalInvoices,
        pendingCount: reportSummary.pendingCount,
        verifiedCount: reportSummary.verifiedCount,
        flaggedCount: reportSummary.flaggedCount,
        verificationRatePercent: reportSummary.verificationRatePercent,
        pendingValue: toNumber(reportSummary.pendingValue),
        verifiedValue: toNumber(reportSummary.verifiedValue),
        flaggedValue: toNumber(reportSummary.flaggedValue),
        totalTaxableValue: toNumber(reportSummary.totalTaxableValue),
        totalCgst: toNumber(reportSummary.totalCgst),
        totalSgst: toNumber(reportSummary.totalSgst),
        totalIgst: toNumber(reportSummary.totalIgst),
        totalInvoiceValue: toNumber(reportSummary.totalInvoiceValue),
      }
    : fallbackMetrics;

  const topSuppliers = [...suppliers]
    .sort((a, b) => b.totalValue - a.totalValue)
    .slice(0, 5);

  const pendingQueue = invoices
    .filter(
      (inv) => inv.status === 'Pending Review' || inv.status === 'Flagged'
    )
    .slice(0, 5);

  const statusBreakdown = [
    {
      label: 'Verified',
      count: metrics.verifiedCount,
      value: metrics.verifiedValue,
      barColor: 'bg-emerald-500',
    },
    {
      label: 'Pending Review',
      count: metrics.pendingCount,
      value: metrics.pendingValue,
      barColor: 'bg-amber-500',
    },
    {
      label: 'Flagged',
      count: metrics.flaggedCount,
      value: metrics.flaggedValue,
      barColor: 'bg-rose-500',
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs text-slate-600">
        <div className="flex items-center gap-2.5">
          <ShieldCheck className="h-4 w-4 shrink-0 text-indigo-600" />
          <span>
            <strong>
              {activeWorkspace?.name ?? 'Active Workspace'} (
              {activeWorkspace?.workspaceCode ?? 'WS'}):
            </strong>{' '}
            Live SQL-backed accounting register with mandatory human review
            sign-off.
          </span>
        </div>
        <button
          type="button"
          onClick={() => navigate('invoices')}
          className="inline-flex shrink-0 items-center gap-1 font-semibold text-indigo-600 hover:text-indigo-700 whitespace-nowrap"
        >
          Manage Invoices
          <ArrowUpRight className="h-3.5 w-3.5" />
        </button>
      </div>

      {reportsError && (
        <div
          role="alert"
          className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900"
        >
          <strong>Summary Report Notice:</strong> {reportsError}
        </div>
      )}

      {workspaceLoading && invoices.length === 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((idx) => (
            <div
              key={idx}
              className="h-28 animate-pulse rounded-xl border border-slate-200 bg-white p-5"
            />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard
            label="Total Invoices"
            value={metrics.totalInvoices}
            sublabel={`${formatINRCompact(metrics.totalInvoiceValue)} total ledger value`}
            icon={<FileText className="h-5 w-5" />}
            tone="slate"
            onClick={() => navigate('invoices')}
          />
          <KpiCard
            label="Pending Reviews"
            value={metrics.pendingCount}
            sublabel={`${formatINRCompact(metrics.pendingValue)} awaiting verification`}
            icon={<Clock className="h-5 w-5" />}
            tone="amber"
            onClick={() => navigate('review')}
          />
          <KpiCard
            label="Verified Invoices"
            value={metrics.verifiedCount}
            sublabel={`${metrics.verificationRatePercent}% verification completion`}
            icon={<CheckCircle2 className="h-5 w-5" />}
            tone="emerald"
            onClick={() => navigate('reports')}
          />
          <KpiCard
            label="Flagged Invoices"
            value={metrics.flaggedCount}
            sublabel={`${formatINRCompact(metrics.flaggedValue)} held for review`}
            icon={<AlertTriangle className="h-5 w-5" />}
            tone="rose"
            onClick={() => navigate('review')}
          />
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <Card className="lg:col-span-7">
          <CardHeader
            title="Invoice Processing Overview"
            subtitle="Taxable value & GST input credit summary across active workspace invoices"
            action={
              <button
                type="button"
                onClick={() => navigate('reports')}
                className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 whitespace-nowrap"
              >
                Full Reports
              </button>
            }
          />
          <div className="space-y-6 p-5">
            <div className="grid grid-cols-2 divide-y divide-slate-100 rounded-lg border border-slate-100 bg-slate-50/70 sm:grid-cols-4 sm:divide-x sm:divide-y-0">
              <div className="p-3.5">
                <p className="text-[11px] font-medium text-slate-500">
                  Taxable Base
                </p>
                <p className="mt-1 font-mono text-sm font-semibold text-slate-900 tabular-nums">
                  {formatINRCompact(metrics.totalTaxableValue)}
                </p>
              </div>
              <div className="p-3.5">
                <p className="text-[11px] font-medium text-slate-500">CGST</p>
                <p className="mt-1 font-mono text-sm font-semibold text-slate-900 tabular-nums">
                  {formatINR(metrics.totalCgst)}
                </p>
              </div>
              <div className="p-3.5">
                <p className="text-[11px] font-medium text-slate-500">SGST</p>
                <p className="mt-1 font-mono text-sm font-semibold text-slate-900 tabular-nums">
                  {formatINR(metrics.totalSgst)}
                </p>
              </div>
              <div className="p-3.5">
                <p className="text-[11px] font-medium text-slate-500">IGST</p>
                <p className="mt-1 font-mono text-sm font-semibold text-slate-900 tabular-nums">
                  {formatINR(metrics.totalIgst)}
                </p>
              </div>
            </div>

            <div>
              <div className="mb-2 flex items-center justify-between text-xs">
                <span className="font-medium text-slate-700">
                  Workspace Verification Progress
                </span>
                <span className="font-mono font-semibold text-slate-900 tabular-nums">
                  {metrics.verifiedCount} / {metrics.totalInvoices} Verified
                </span>
              </div>
              <div className="flex h-2.5 w-full overflow-hidden rounded-md bg-slate-100">
                {metrics.totalInvoices > 0 && (
                  <>
                    <div
                      style={{
                        width: `${(metrics.verifiedCount / metrics.totalInvoices) * 100}%`,
                      }}
                      className="bg-emerald-500 transition-all"
                      title="Verified"
                    />
                    <div
                      style={{
                        width: `${(metrics.pendingCount / metrics.totalInvoices) * 100}%`,
                      }}
                      className="bg-amber-400 transition-all"
                      title="Pending Review"
                    />
                    <div
                      style={{
                        width: `${(metrics.flaggedCount / metrics.totalInvoices) * 100}%`,
                      }}
                      className="bg-rose-500 transition-all"
                      title="Flagged"
                    />
                  </>
                )}
              </div>
            </div>
          </div>
        </Card>

        <Card className="lg:col-span-5">
          <CardHeader
            title="Invoice Status Breakdown"
            subtitle="Counts & INR value by human verification stage"
          />
          <div className="divide-y divide-slate-100 px-5 py-2">
            {statusBreakdown.map((item) => {
              const pct =
                metrics.totalInvoices > 0
                  ? Math.round((item.count / metrics.totalInvoices) * 100)
                  : 0;
              return (
                <div key={item.label} className="py-3.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-medium text-slate-800">
                      {item.label}
                    </span>
                    <div className="text-right font-mono tabular-nums">
                      <span className="font-semibold text-slate-900">
                        {item.count}
                      </span>
                      <span className="ml-1.5 text-slate-400">({pct}%)</span>
                    </div>
                  </div>
                  <div className="mt-2 flex items-center justify-between gap-3 text-[11px] text-slate-500">
                    <div className="h-1.5 flex-1 overflow-hidden rounded-sm bg-slate-100">
                      <div
                        style={{ width: `${pct}%` }}
                        className={`h-full ${item.barColor}`}
                      />
                    </div>
                    <span className="font-mono font-medium tabular-nums">
                      {formatINR(item.value)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <Card className="lg:col-span-6">
          <CardHeader
            title="Pending Review Queue"
            subtitle="Invoices requiring CA / finance team sign-off"
            action={
              <button
                type="button"
                onClick={() => navigate('review')}
                className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 whitespace-nowrap"
              >
                Open Review Centre
              </button>
            }
          />
          <div className="divide-y divide-slate-100">
            {pendingQueue.length === 0 ? (
              <p className="px-5 py-8 text-center text-xs text-slate-500">
                No pending or flagged invoices in this workspace.
              </p>
            ) : (
              pendingQueue.map((inv) => (
                <div
                  key={inv.id}
                  className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5 hover:bg-slate-50/70 sm:flex-nowrap"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2.5">
                      <span className="font-mono text-xs font-semibold text-slate-900">
                        {inv.invoiceNumber}
                      </span>
                      <StatusBadge status={inv.status} />
                    </div>
                    <p className="mt-1 truncate text-xs text-slate-500">
                      {inv.supplierName} ·{' '}
                      {inv.invoiceDate
                        ? formatDateIN(inv.invoiceDate)
                        : 'No invoice date'}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <span className="font-mono text-xs font-semibold text-slate-900 tabular-nums">
                      {formatINR(inv.totalAmount)}
                    </span>
                    <button
                      type="button"
                      onClick={() => selectInvoiceForReview(inv.id)}
                      className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:border-indigo-300 hover:text-indigo-700 whitespace-nowrap"
                    >
                      Review
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </Card>

        <Card className="lg:col-span-6">
          <CardHeader
            title="Recent Audit Activity"
            subtitle="Immutable workspace event log across uploads, edits, reviews, and exports"
            action={
              <button
                type="button"
                onClick={() => navigate('reports')}
                className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 whitespace-nowrap"
              >
                Full Trail
              </button>
            }
          />
          <div className="divide-y divide-slate-100">
            {activities.length === 0 ? (
              <p className="px-5 py-8 text-center text-xs text-slate-500">
                No audit events recorded yet in this workspace.
              </p>
            ) : (
              activities.slice(0, 5).map((act) => (
                <div
                  key={act.id}
                  className="flex items-start gap-3 px-5 py-3.5"
                >
                  <div className="mt-0.5 shrink-0">
                    {act.tone === 'success' ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                    ) : act.tone === 'warning' ? (
                      <AlertTriangle className="h-4 w-4 text-rose-600" />
                    ) : (
                      <Clock className="h-4 w-4 text-indigo-600" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center justify-between gap-1">
                      <span className="text-xs font-semibold text-slate-900">
                        {act.actor}
                      </span>
                      <span className="text-[11px] text-slate-400 tabular-nums">
                        {act.timestamp}
                      </span>
                    </div>
                    <p className="mt-0.5 text-xs text-slate-600">
                      {act.action}
                    </p>
                    {act.invoiceId && (
                      <button
                        type="button"
                        onClick={() => selectInvoiceForReview(act.invoiceId!)}
                        className="mt-1 text-[11px] font-medium text-indigo-600 hover:underline"
                      >
                        Open Invoice in Review Centre
                      </button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Top Suppliers by Ledger Value"
          subtitle="Active vendors in the selected workspace"
          action={
            <button
              type="button"
              onClick={() => navigate('suppliers')}
              className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 whitespace-nowrap"
            >
              View All Suppliers
            </button>
          }
        />
        {topSuppliers.length === 0 ? (
          <p className="px-5 py-8 text-center text-xs text-slate-500">
            No suppliers recorded in this workspace yet.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/70 text-slate-500">
                  <th className="px-5 py-3 font-medium">Supplier</th>
                  <th className="px-5 py-3 font-medium">GSTIN</th>
                  <th className="px-5 py-3 font-medium">Category</th>
                  <th className="px-5 py-3 text-right font-medium">
                    Invoices
                  </th>
                  <th className="px-5 py-3 text-right font-medium">
                    Total Value
                  </th>
                  <th className="px-5 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {topSuppliers.map((sup) => (
                  <tr key={sup.id} className="hover:bg-slate-50/60">
                    <td className="px-5 py-3 font-medium text-slate-900">
                      {sup.name}
                    </td>
                    <td className="px-5 py-3 font-mono text-slate-600">
                      {sup.gstin || '—'}
                    </td>
                    <td className="px-5 py-3 text-slate-600">{sup.category}</td>
                    <td className="px-5 py-3 text-right font-mono tabular-nums text-slate-700">
                      {sup.totalInvoices}
                    </td>
                    <td className="px-5 py-3 text-right font-mono font-medium tabular-nums text-slate-900">
                      {formatINR(sup.totalValue)}
                    </td>
                    <td className="px-5 py-3">
                      <StatusBadge status={sup.status} />
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
