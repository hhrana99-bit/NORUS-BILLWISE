import { BarChart3, Check, Download, FileSpreadsheet } from 'lucide-react';
import { useState } from 'react';
import { Card, CardHeader } from '../components/common/Card';
import { formatINR, formatINRCompact } from '../services/formatters';
import {
  buildMonthlyTrendStats,
  computeReportMetrics,
  exportInvoicesToCsv,
  type TrendWindowOption,
} from '../services/reportService';
import { useWorkspace } from '../state/WorkspaceContext';

export function ReportsPage() {
  const { invoices, settings, selectInvoiceForReview } = useWorkspace();
  const [exportedMessage, setExportedMessage] = useState(false);
  const [trendWindow, setTrendWindow] = useState<TrendWindowOption>(6);

  const metrics = computeReportMetrics(invoices);
  const monthlyTrends = buildMonthlyTrendStats(invoices, {
    windowMonths: trendWindow,
  });
  const flaggedList = invoices.filter((inv) => inv.status === 'Flagged');

  const maxMonthlyCount = Math.max(1, ...monthlyTrends.map((m) => m.totalCount));
  const chartCountTotal = monthlyTrends.reduce((sum, m) => sum + m.totalCount, 0);
  const rangeSubtitle =
    monthlyTrends.length > 0
      ? `${monthlyTrends[0].label} – ${monthlyTrends[monthlyTrends.length - 1].label} · ${chartCountTotal} of ${metrics.totalInvoices} invoices`
      : 'No valid invoice dates available';

  const handleExportCsv = () => {
    exportInvoicesToCsv(invoices, settings.workspaceName);
    setExportedMessage(true);
    setTimeout(() => setExportedMessage(false), 3000);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">
            Verification &amp; GST Summary Reports
          </h2>
          <p className="text-xs text-slate-500">
            Live accounting summary across your local prototype invoice register.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={handleExportCsv}
            className="inline-flex h-10 items-center gap-2 rounded-lg bg-slate-900 px-4 text-xs font-semibold text-white hover:bg-slate-800 whitespace-nowrap"
          >
            {exportedMessage ? (
              <>
                <Check className="h-4 w-4 text-emerald-400" />
                CSV Downloaded
              </>
            ) : (
              <>
                <Download className="h-4 w-4" />
                Export CSV Report
              </>
            )}
          </button>
          <button
            type="button"
            disabled
            title="Excel (.xlsx) export will be added with backend integration"
            className="inline-flex h-10 cursor-not-allowed items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-3 text-xs font-medium text-slate-400 whitespace-nowrap"
          >
            <FileSpreadsheet className="h-4 w-4" />
            Excel (Planned)
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="p-5">
          <p className="text-xs font-medium text-slate-500">Processed Invoice Value</p>
          <p className="mt-2 font-mono text-xl font-semibold text-slate-900 tabular-nums">
            {formatINR(metrics.totalInvoiceValue)}
          </p>
          <p className="mt-1 text-xs text-slate-500 tabular-nums">
            {metrics.totalInvoices} total documents
          </p>
        </Card>
        <Card className="p-5">
          <p className="text-xs font-medium text-slate-500">Total Input GST</p>
          <p className="mt-2 font-mono text-xl font-semibold text-slate-900 tabular-nums">
            {formatINR(metrics.totalGst)}
          </p>
          <p className="mt-1 text-xs text-slate-500">CGST + SGST + IGST combined</p>
        </Card>
        <Card className="p-5">
          <p className="text-xs font-medium text-slate-500">Verified Value</p>
          <p className="mt-2 font-mono text-xl font-semibold text-emerald-700 tabular-nums">
            {formatINR(metrics.verifiedValue)}
          </p>
          <p className="mt-1 text-xs text-slate-500 tabular-nums">
            {metrics.verifiedCount} verified records
          </p>
        </Card>
        <Card className="p-5">
          <p className="text-xs font-medium text-slate-500">Flagged Value Held</p>
          <p className="mt-2 font-mono text-xl font-semibold text-rose-700 tabular-nums">
            {formatINR(metrics.flaggedValue)}
          </p>
          <p className="mt-1 text-xs text-slate-500 tabular-nums">
            {metrics.flaggedCount} flagged invoices
          </p>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <Card className="lg:col-span-7">
          <CardHeader
            title="Monthly Invoice Volume Trend"
            subtitle={rangeSubtitle}
            action={
              <div
                role="group"
                aria-label="Reporting window"
                className="flex items-center gap-1 rounded-lg bg-slate-100 p-1"
              >
                {(
                  [
                    { label: '6M', value: 6 },
                    { label: '12M', value: 12 },
                    { label: 'All', value: 'all' },
                  ] as const
                ).map((option) => (
                  <button
                    key={option.label}
                    type="button"
                    onClick={() => setTrendWindow(option.value)}
                    className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors whitespace-nowrap ${
                      trendWindow === option.value
                        ? 'bg-white text-slate-900 shadow-xs'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            }
          />
          <div className="p-5">
            {monthlyTrends.length === 0 ? (
              <div className="flex h-60 flex-col items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50/70 px-4 text-center">
                <BarChart3 className="h-6 w-6 text-slate-400" />
                <p className="mt-2 text-xs font-semibold text-slate-800">
                  No dated invoices to chart
                </p>
                <p className="mt-1 text-[11px] text-slate-500">
                  Invoices with valid YYYY-MM-DD dates appear automatically in this
                  chronological chart.
                </p>
              </div>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <div className="min-w-[360px]">
                    <div className="flex h-60 items-end justify-between gap-2 border-b border-slate-200 pb-3 pt-4 sm:gap-3">
                      {monthlyTrends.map((month) => {
                        const verifiedH = Math.round(
                          (month.verifiedCount / maxMonthlyCount) * 180
                        );
                        const pendingH = Math.round(
                          (month.pendingCount / maxMonthlyCount) * 180
                        );
                        const flaggedH = Math.round(
                          (month.flaggedCount / maxMonthlyCount) * 180
                        );

                        return (
                          <div
                            key={month.monthKey}
                            className="flex flex-1 flex-col items-center gap-2"
                          >
                            <span className="font-mono text-[11px] font-semibold text-slate-700 tabular-nums">
                              {month.totalCount}
                            </span>
                            <div className="flex w-full max-w-[42px] flex-col-reverse overflow-hidden rounded-t-md bg-slate-100">
                              {verifiedH > 0 && (
                                <div
                                  style={{ height: `${verifiedH}px` }}
                                  className="w-full bg-emerald-500"
                                  title={`Verified: ${month.verifiedCount}`}
                                />
                              )}
                              {pendingH > 0 && (
                                <div
                                  style={{ height: `${pendingH}px` }}
                                  className="w-full bg-amber-400"
                                  title={`Pending: ${month.pendingCount}`}
                                />
                              )}
                              {flaggedH > 0 && (
                                <div
                                  style={{ height: `${flaggedH}px` }}
                                  className="w-full bg-rose-500"
                                  title={`Flagged: ${month.flaggedCount}`}
                                />
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    <div className="mt-2 flex justify-between gap-2 text-center sm:gap-3">
                      {monthlyTrends.map((month) => (
                        <div key={month.monthKey} className="min-w-0 flex-1">
                          <p className="truncate text-xs font-medium text-slate-700">
                            {month.label}
                          </p>
                          <p className="truncate font-mono text-[10px] text-slate-400 tabular-nums">
                            {formatINRCompact(month.totalValue)}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-600">
                  <div className="flex flex-wrap items-center gap-4">
                    <span className="inline-flex items-center gap-1.5">
                      <span className="h-2.5 w-2.5 rounded-xs bg-emerald-500" />
                      Verified
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                      <span className="h-2.5 w-2.5 rounded-xs bg-amber-400" />
                      Pending Review
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                      <span className="h-2.5 w-2.5 rounded-xs bg-rose-500" />
                      Flagged
                    </span>
                  </div>
                  {chartCountTotal !== metrics.totalInvoices && (
                    <span className="text-[11px] text-amber-700">
                      {metrics.totalInvoices - chartCountTotal} invoice(s) outside window
                      or undated
                    </span>
                  )}
                </div>
              </>
            )}
          </div>
        </Card>

        <Card className="lg:col-span-5">
          <CardHeader
            title="Verified vs. Pending vs. Flagged"
            subtitle="Verification split of current sample register"
          />
          <div className="space-y-5 p-5">
            <div className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 p-4">
              <div>
                <p className="text-xs font-medium text-slate-500">
                  Verification Completion Rate
                </p>
                <p className="mt-1 font-mono text-3xl font-bold text-slate-900 tabular-nums">
                  {metrics.verificationRatePercent}%
                </p>
              </div>
              <div className="text-right font-mono text-xs text-slate-600 tabular-nums">
                <p>Verified: {metrics.verifiedCount}</p>
                <p>Pending: {metrics.pendingCount}</p>
                <p>Flagged: {metrics.flaggedCount}</p>
              </div>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <div className="mb-1 flex justify-between">
                  <span className="font-medium text-slate-700">Verified</span>
                  <span className="font-mono tabular-nums text-slate-600">
                    {formatINR(metrics.verifiedValue)}
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-sm bg-slate-100">
                  <div
                    style={{
                      width: `${
                        metrics.totalInvoices > 0
                          ? (metrics.verifiedCount / metrics.totalInvoices) * 100
                          : 0
                      }%`,
                    }}
                    className="h-full bg-emerald-500"
                  />
                </div>
              </div>

              <div>
                <div className="mb-1 flex justify-between">
                  <span className="font-medium text-slate-700">Pending Review</span>
                  <span className="font-mono tabular-nums text-slate-600">
                    {formatINR(metrics.pendingValue)}
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-sm bg-slate-100">
                  <div
                    style={{
                      width: `${
                        metrics.totalInvoices > 0
                          ? (metrics.pendingCount / metrics.totalInvoices) * 100
                          : 0
                      }%`,
                    }}
                    className="h-full bg-amber-400"
                  />
                </div>
              </div>

              <div>
                <div className="mb-1 flex justify-between">
                  <span className="font-medium text-slate-700">Flagged</span>
                  <span className="font-mono tabular-nums text-slate-600">
                    {formatINR(metrics.flaggedValue)}
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-sm bg-slate-100">
                  <div
                    style={{
                      width: `${
                        metrics.totalInvoices > 0
                          ? (metrics.flaggedCount / metrics.totalInvoices) * 100
                          : 0
                      }%`,
                    }}
                    className="h-full bg-rose-500"
                  />
                </div>
              </div>
            </div>
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Flagged Invoices Exception Report"
          subtitle="Exceptions requiring resolution before accounting export"
        />
        {flaggedList.length === 0 ? (
          <p className="px-5 py-8 text-center text-xs text-slate-500">
            No flagged invoices currently in queue.
          </p>
        ) : (
          <div className="divide-y divide-slate-100">
            {flaggedList.map((inv) => (
              <div
                key={inv.id}
                className="flex flex-wrap items-center justify-between gap-3 px-5 py-4"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs font-semibold text-slate-900">
                      {inv.invoiceNumber}
                    </span>
                    <span className="text-xs text-slate-500">
                      · {inv.supplierName}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-rose-700">
                    {inv.flagReason || 'Flagged for manual audit review.'}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="font-mono text-xs font-semibold tabular-nums text-slate-900">
                    {formatINR(inv.totalAmount)}
                  </span>
                  <button
                    type="button"
                    onClick={() => selectInvoiceForReview(inv.id)}
                    className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:border-indigo-300 hover:text-indigo-700 whitespace-nowrap"
                  >
                    Resolve
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
