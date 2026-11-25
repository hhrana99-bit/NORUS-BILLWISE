import {
  AlertCircle,
  BarChart3,
  Check,
  ChevronLeft,
  ChevronRight,
  Download,
  FileSpreadsheet,
  History,
  Info,
  Lock,
  Search,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Card, CardHeader } from '../components/common/Card';
import { DEMO_MODE_DISABLED_ACTION_MESSAGE } from '../config/demoMode';
import { apiClient, formatApiErrorMessage } from '../services/apiClient';
import {
  listDemoAuditEvents,
  listDemoReportExceptions,
} from '../services/demoDataService';
import { formatDateIN, formatINR, formatINRCompact } from '../services/formatters';
import { useWorkspace } from '../state/WorkspaceContext';
import type {
  ApiAuditEvent,
  ApiReportExceptionItem,
  FlagCategory,
} from '../types/domain';

function toNumber(val: string | number | undefined | null): number {
  if (val === null || val === undefined || val === '') return 0;
  const parsed = Number(val);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function ReportsPage() {
  const {
    isDemoMode,
    activeWorkspaceId,
    activeWorkspaceRole,
    reportSummary,
    monthlyTrend,
    monthlyTrendMeta,
    reportsError,
    loadTrendWindow,
    exportCsvReport,
    selectInvoiceForReview,
  } = useWorkspace();

  const [trendWindow, setTrendWindow] = useState<'6m' | '12m' | 'all'>(
    monthlyTrendMeta.window
  );
  const [trendLoading, setTrendLoading] = useState(false);

  const [exSearch, setExSearch] = useState('');
  const [exStatus, setExStatus] = useState<'' | 'PENDING_REVIEW' | 'FLAGGED'>('');
  const [exCategory, setExCategory] = useState<'' | FlagCategory>('');
  const [exPage, setExPage] = useState(1);
  const [exceptions, setExceptions] = useState<ApiReportExceptionItem[]>([]);
  const [exceptionsTotal, setExceptionsTotal] = useState(0);
  const [exceptionsLoading, setExceptionsLoading] = useState(false);
  const [exceptionsError, setExceptionsError] = useState<string | null>(null);

  const [auditEventType, setAuditEventType] = useState('');
  const [auditPage, setAuditPage] = useState(1);
  const [auditRows, setAuditRows] = useState<ApiAuditEvent[]>([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState<string | null>(null);

  const [exporting, setExporting] = useState(false);
  const [exportedMessage, setExportedMessage] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const canExportCsv =
    !isDemoMode &&
    (activeWorkspaceRole === 'WORKSPACE_ADMIN' ||
      activeWorkspaceRole === 'REVIEWER' ||
      activeWorkspaceRole === 'VIEWER');

  const fetchExceptions = useCallback(
    async (signal?: AbortSignal) => {
      if (!activeWorkspaceId) return;
      if (isDemoMode) {
        const res = listDemoReportExceptions({
          search: exSearch.trim() || undefined,
          status: exStatus,
          flagCategory: exCategory,
          page: exPage,
          pageSize: 10,
        });
        setExceptions(res.items);
        setExceptionsTotal(res.total);
        setExceptionsError(null);
        setExceptionsLoading(false);
        return;
      }

      setExceptionsLoading(true);
      setExceptionsError(null);
      try {
        const res = await apiClient.listReportExceptions(
          activeWorkspaceId,
          {
            search: exSearch.trim() || undefined,
            status: exStatus || undefined,
            flagCategory: exCategory || undefined,
            page: exPage,
            pageSize: 10,
          },
          signal
        );
        if (signal?.aborted) return;
        setExceptions(res.items);
        setExceptionsTotal(res.total);
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return;
        setExceptionsError(formatApiErrorMessage(err));
      } finally {
        if (!signal?.aborted) setExceptionsLoading(false);
      }
    },
    [activeWorkspaceId, exCategory, exPage, exSearch, exStatus, isDemoMode]
  );

  const fetchAuditTrail = useCallback(
    async (signal?: AbortSignal) => {
      if (!activeWorkspaceId) return;
      if (isDemoMode) {
        const res = listDemoAuditEvents({
          eventType: auditEventType.trim() || undefined,
          page: auditPage,
          pageSize: 15,
        });
        setAuditRows(res.items);
        setAuditTotal(res.total);
        setAuditError(null);
        setAuditLoading(false);
        return;
      }

      setAuditLoading(true);
      setAuditError(null);
      try {
        const res = await apiClient.listAuditEvents(
          activeWorkspaceId,
          {
            eventType: auditEventType.trim() || undefined,
            page: auditPage,
            pageSize: 15,
          },
          signal
        );
        if (signal?.aborted) return;
        setAuditRows(res.items);
        setAuditTotal(res.total);
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return;
        setAuditError(formatApiErrorMessage(err));
      } finally {
        if (!signal?.aborted) setAuditLoading(false);
      }
    },
    [activeWorkspaceId, auditEventType, auditPage, isDemoMode]
  );

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      void fetchExceptions(controller.signal);
    }, 150);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [fetchExceptions]);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      void fetchAuditTrail(controller.signal);
    }, 150);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [fetchAuditTrail]);

  const handleWindowChange = async (win: '6m' | '12m' | 'all') => {
    setTrendWindow(win);
    setTrendLoading(true);
    try {
      await loadTrendWindow(win);
    } finally {
      setTrendLoading(false);
    }
  };

  const handleExportCsv = async () => {
    if (!canExportCsv) return;
    setExportError(null);
    setExporting(true);
    try {
      await exportCsvReport();
      setExportedMessage(true);
      setTimeout(() => setExportedMessage(false), 3000);
      void fetchAuditTrail();
    } catch (err) {
      setExportError(formatApiErrorMessage(err));
    } finally {
      setExporting(false);
    }
  };

  const metrics = {
    totalInvoices: reportSummary?.totalInvoices ?? 0,
    pendingCount: reportSummary?.pendingCount ?? 0,
    verifiedCount: reportSummary?.verifiedCount ?? 0,
    flaggedCount: reportSummary?.flaggedCount ?? 0,
    verificationRatePercent: reportSummary?.verificationRatePercent ?? 0,
    pendingValue: toNumber(reportSummary?.pendingValue),
    verifiedValue: toNumber(reportSummary?.verifiedValue),
    flaggedValue: toNumber(reportSummary?.flaggedValue),
    totalGst: toNumber(reportSummary?.totalGst),
    totalInvoiceValue: toNumber(reportSummary?.totalInvoiceValue),
    openFlagCount: reportSummary?.openFlagCount ?? 0,
  };

  const maxMonthlyCount = Math.max(
    1,
    ...monthlyTrend.map((m) => m.totalCount)
  );
  const chartCountTotal = monthlyTrend.reduce(
    (sum, m) => sum + m.totalCount,
    0
  );
  const rangeSubtitle =
    monthlyTrend.length > 0
      ? `${monthlyTrend[0].label} – ${monthlyTrend[monthlyTrend.length - 1].label} · ${chartCountTotal} of ${metrics.totalInvoices} invoices`
      : 'No dated invoices available';

  const exTotalPages = Math.max(1, Math.ceil(exceptionsTotal / 10));
  const auditTotalPages = Math.max(1, Math.ceil(auditTotal / 15));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">
            Verification &amp; GST Summary Reports
          </h2>
          <p className="text-xs text-slate-500">
            Server-aggregated operational accounting metrics, exception feed,
            formula-safe CSV export, and audit trail.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={!canExportCsv || exporting}
            onClick={() => void handleExportCsv()}
            title={
              isDemoMode
                ? DEMO_MODE_DISABLED_ACTION_MESSAGE
                : canExportCsv
                  ? 'Download formula-safe UTF-8 CSV from server'
                  : 'CSV export requires VIEWER, REVIEWER, or WORKSPACE_ADMIN role'
            }
            className="inline-flex h-10 items-center gap-2 rounded-lg bg-slate-900 px-4 text-xs font-semibold text-white hover:bg-slate-800 whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-50"
          >
            {exportedMessage ? (
              <>
                <Check className="h-4 w-4 text-emerald-400" />
                CSV Downloaded
              </>
            ) : (
              <>
                <Download className="h-4 w-4" />
                {exporting ? 'Exporting CSV...' : 'Export CSV Report'}
              </>
            )}
          </button>
          <button
            type="button"
            disabled
            title="Excel (.xlsx) export is planned in a future release"
            className="inline-flex h-10 cursor-not-allowed items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-3 text-xs font-medium text-slate-400 whitespace-nowrap"
          >
            <FileSpreadsheet className="h-4 w-4" />
            Excel (Planned)
          </button>
        </div>
      </div>

      {isDemoMode && (
        <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-100 px-4 py-2.5 text-xs text-slate-700">
          <Lock className="h-4 w-4 shrink-0 text-slate-500" />
          <span>
            <strong>Demo Mode (Sample Data):</strong> Explore sample KPIs,
            monthly trend windows, exception filters, and audit history. Server
            CSV export is unavailable in read-only demo preview.
          </span>
        </div>
      )}

      <div className="flex items-start gap-2.5 rounded-xl border border-indigo-200 bg-indigo-50/70 px-4 py-3 text-xs text-indigo-950">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-indigo-600" />
        <p>
          <strong>Operational Verification Summary:</strong>{' '}
          {reportSummary?.disclaimer ??
            'Operational verification and GST input-credit summary only; not a statutory GST return or official GSTR filing.'}
        </p>
      </div>

      {(reportsError || exportError) && (
        <div
          role="alert"
          className="flex items-center gap-2 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-900"
        >
          <AlertCircle className="h-4 w-4 shrink-0 text-rose-600" />
          <span>{exportError ?? reportsError}</span>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="p-5">
          <p className="text-xs font-medium text-slate-500">
            Processed Invoice Value
          </p>
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
          <p className="mt-1 text-xs text-slate-500">
            CGST + SGST + IGST + Cess
          </p>
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
          <p className="text-xs font-medium text-slate-500">
            Flagged Value Held
          </p>
          <p className="mt-2 font-mono text-xl font-semibold text-rose-700 tabular-nums">
            {formatINR(metrics.flaggedValue)}
          </p>
          <p className="mt-1 text-xs text-slate-500 tabular-nums">
            {metrics.flaggedCount} flagged · {metrics.openFlagCount} open flags
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
                    { label: '6M', value: '6m' },
                    { label: '12M', value: '12m' },
                    { label: 'All', value: 'all' },
                  ] as const
                ).map((option) => (
                  <button
                    key={option.label}
                    type="button"
                    disabled={trendLoading}
                    onClick={() => void handleWindowChange(option.value)}
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
            {monthlyTrend.length === 0 ? (
              <div className="flex h-60 flex-col items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50/70 px-4 text-center">
                <BarChart3 className="h-6 w-6 text-slate-400" />
                <p className="mt-2 text-xs font-semibold text-slate-800">
                  No dated invoices to chart
                </p>
                <p className="mt-1 text-[11px] text-slate-500">
                  Invoices with valid invoice dates appear automatically in this
                  SQL-aggregated chronological chart.
                </p>
              </div>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <div className="min-w-[360px]">
                    <div className="flex h-60 items-end justify-between gap-2 border-b border-slate-200 pb-3 pt-4 sm:gap-3">
                      {monthlyTrend.map((month) => {
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
                      {monthlyTrend.map((month) => (
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
                  {(monthlyTrendMeta.excludedCount > 0 ||
                    monthlyTrendMeta.outOfWindowCount > 0) && (
                    <span className="text-[11px] text-amber-700">
                      {monthlyTrendMeta.excludedCount} undated ·{' '}
                      {monthlyTrendMeta.outOfWindowCount} outside window
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
            subtitle="Verification split of workspace accounting ledger"
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
                          ? (metrics.verifiedCount / metrics.totalInvoices) *
                            100
                          : 0
                      }%`,
                    }}
                    className="h-full bg-emerald-500"
                  />
                </div>
              </div>

              <div>
                <div className="mb-1 flex justify-between">
                  <span className="font-medium text-slate-700">
                    Pending Review
                  </span>
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
          title="Exceptions & Flagged Invoices Feed"
          subtitle="Flagged invoices and unresolved variance records requiring human attention"
        />
        <div className="flex flex-wrap items-center gap-2.5 border-b border-slate-100 px-5 py-3">
          <div className="relative w-full min-w-0 sm:min-w-[200px] sm:flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={exSearch}
              onChange={(e) => {
                setExSearch(e.target.value);
                setExPage(1);
              }}
              placeholder="Search exceptions by invoice, supplier, GSTIN..."
              className="h-9 w-full rounded-lg border border-slate-200 bg-slate-50 pl-8 pr-3 text-xs"
            />
          </div>
          <select
            value={exStatus}
            onChange={(e) => {
              setExStatus(
                e.target.value as '' | 'PENDING_REVIEW' | 'FLAGGED'
              );
              setExPage(1);
            }}
            aria-label="Filter exceptions by status"
            className="h-9 rounded-lg border border-slate-200 bg-white px-2.5 text-xs"
          >
            <option value="">All Exception Statuses</option>
            <option value="FLAGGED">Flagged</option>
            <option value="PENDING_REVIEW">Pending Review (Variance)</option>
          </select>
          <select
            value={exCategory}
            onChange={(e) => {
              setExCategory(e.target.value as '' | FlagCategory);
              setExPage(1);
            }}
            aria-label="Filter exceptions by flag category"
            className="h-9 rounded-lg border border-slate-200 bg-white px-2.5 text-xs"
          >
            <option value="">All Flag Categories</option>
            <option value="ARITHMETIC_MISMATCH">Arithmetic Mismatch</option>
            <option value="DUPLICATE_SUSPICION">Duplicate Suspicion</option>
            <option value="GSTIN_ISSUE">GSTIN Issue</option>
            <option value="HSN_RATE_MISMATCH">HSN/Rate Mismatch</option>
            <option value="MISSING_PO_GRN">Missing PO/GRN</option>
            <option value="CUSTOM">Custom</option>
          </select>
        </div>

        {exceptionsError ? (
          <p className="px-5 py-6 text-xs text-rose-700">{exceptionsError}</p>
        ) : exceptionsLoading && exceptions.length === 0 ? (
          <p className="px-5 py-6 text-center text-xs text-slate-500">
            Loading exceptions feed...
          </p>
        ) : exceptions.length === 0 ? (
          <p className="px-5 py-8 text-center text-xs text-slate-500">
            No flagged or unresolved variance exceptions match your filters.
          </p>
        ) : (
          <div className="divide-y divide-slate-100">
            {exceptions.map((item) => (
              <div
                key={item.invoiceId}
                className="flex flex-wrap items-center justify-between gap-3 px-5 py-4"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs font-semibold text-slate-900">
                      {item.invoiceNumber}
                    </span>
                    <span className="text-xs text-slate-500">
                      · {item.supplierName}
                    </span>
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-700">
                      {item.reconciliationStatus}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-rose-700">
                    {item.openFlags[0]?.reasonText ??
                      `Reconciliation variance of ${formatINR(toNumber(item.varianceAmount))}`}
                  </p>
                  {item.lastAction && (
                    <p className="mt-0.5 text-[11px] text-slate-400">
                      Last action: {item.lastAction.actionType} by{' '}
                      {item.lastAction.actorDisplayName}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  <span className="font-mono text-xs font-semibold tabular-nums text-slate-900">
                    {formatINR(toNumber(item.totalAmount))}
                  </span>
                  <button
                    type="button"
                    onClick={() => selectInvoiceForReview(item.invoiceId)}
                    className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:border-indigo-300 hover:text-indigo-700 whitespace-nowrap"
                  >
                    Resolve
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 px-5 py-3 text-xs text-slate-500">
          <span>
            {exceptionsTotal} exception record(s)
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={exPage <= 1}
              onClick={() => setExPage((p) => Math.max(1, p - 1))}
              className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-700 disabled:opacity-40"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              Prev
            </button>
            <span className="font-mono text-xs tabular-nums">
              Page {exPage} / {exTotalPages}
            </span>
            <button
              type="button"
              disabled={exPage >= exTotalPages}
              onClick={() => setExPage((p) => Math.min(exTotalPages, p + 1))}
              className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-700 disabled:opacity-40"
            >
              Next
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Workspace Audit Trail"
          subtitle={
            activeWorkspaceRole === 'UPLOADER'
              ? 'Showing your own actor audit events (Uploader scope)'
              : 'Append-only workspace activity ledger (uploads, edits, approvals, exports)'
          }
          action={
            <input
              type="text"
              value={auditEventType}
              onChange={(e) => {
                setAuditEventType(e.target.value);
                setAuditPage(1);
              }}
              placeholder="Filter event type (e.g. invoice.verified)"
              aria-label="Filter audit events by event type"
              className="h-9 w-full rounded-lg border border-slate-200 bg-slate-50 px-2.5 font-mono text-[11px] sm:w-56"
            />
          }
        />

        {auditError ? (
          <p className="px-5 py-6 text-xs text-rose-700">{auditError}</p>
        ) : auditLoading && auditRows.length === 0 ? (
          <p className="px-5 py-6 text-center text-xs text-slate-500">
            Loading audit trail...
          </p>
        ) : auditRows.length === 0 ? (
          <p className="px-5 py-8 text-center text-xs text-slate-500">
            No audit events matched your filter.
          </p>
        ) : (
          <div className="divide-y divide-slate-100">
            {auditRows.map((evt) => (
              <div
                key={evt.id}
                className="flex flex-wrap items-start justify-between gap-2 px-5 py-3 text-xs"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <History className="h-3.5 w-3.5 text-slate-400" />
                    <span className="font-semibold text-slate-900">
                      {evt.actorDisplayName}
                    </span>
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-700">
                      {evt.eventType}
                    </span>
                  </div>
                  <p className="mt-0.5 text-slate-600">{evt.summary}</p>
                </div>
                <span className="shrink-0 font-mono text-[11px] text-slate-400 tabular-nums">
                  {formatDateIN(evt.createdAt.slice(0, 10))}{' '}
                  {new Date(evt.createdAt).toLocaleTimeString('en-IN', {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 px-5 py-3 text-xs text-slate-500">
          <span>{auditTotal} audit event(s)</span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={auditPage <= 1}
              onClick={() => setAuditPage((p) => Math.max(1, p - 1))}
              className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-700 disabled:opacity-40"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              Prev
            </button>
            <span className="font-mono text-xs tabular-nums">
              Page {auditPage} / {auditTotalPages}
            </span>
            <button
              type="button"
              disabled={auditPage >= auditTotalPages}
              onClick={() =>
                setAuditPage((p) => Math.min(auditTotalPages, p + 1))
              }
              className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-700 disabled:opacity-40"
            >
              Next
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </Card>
    </div>
  );
}
