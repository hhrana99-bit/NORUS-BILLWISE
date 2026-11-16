import { Bell, Check, Menu, Search } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { formatINR } from '../../services/formatters';
import { useWorkspace } from '../../state/WorkspaceContext';
import type { AppRoute } from '../../types/domain';

const ROUTE_TITLES: Record<AppRoute, string> = {
  dashboard: 'Dashboard',
  invoices: 'Invoices',
  review: 'Review Centre',
  suppliers: 'Suppliers',
  reports: 'Reports',
  settings: 'Settings',
};

export function TopBar({ onOpenMobileNav }: { onOpenMobileNav: () => void }) {
  const {
    activeRoute,
    settings,
    invoices,
    suppliers,
    notifications,
    navigate,
    selectInvoiceForReview,
    markNotificationRead,
    markAllNotificationsRead,
  } = useWorkspace();

  const [globalQuery, setGlobalQuery] = useState('');
  const [searchFocused, setSearchFocused] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);
  const notifRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleOutside = (event: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(event.target as Node)) {
        setSearchFocused(false);
      }
      if (notifRef.current && !notifRef.current.contains(event.target as Node)) {
        setNotifOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutside);
    return () => document.removeEventListener('mousedown', handleOutside);
  }, []);

  const unreadCount = notifications.filter((n) => !n.read).length;
  const trimmed = globalQuery.trim().toLowerCase();

  const matchedInvoices = trimmed
    ? invoices
        .filter((inv) =>
          `${inv.invoiceNumber} ${inv.supplierName} ${inv.supplierGstin}`
            .toLowerCase()
            .includes(trimmed)
        )
        .slice(0, 4)
    : [];

  const matchedSuppliers = trimmed
    ? suppliers
        .filter((sup) =>
          `${sup.name} ${sup.gstin} ${sup.category}`.toLowerCase().includes(trimmed)
        )
        .slice(0, 3)
    : [];

  return (
    <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center justify-between gap-4 border-b border-slate-200 bg-white px-4 sm:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          onClick={onOpenMobileNav}
          className="flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 lg:hidden"
          aria-label="Open navigation menu"
        >
          <Menu className="h-4 w-4" />
        </button>

        <div className="flex min-w-0 items-center gap-2 text-sm">
          <h1 className="truncate font-semibold text-slate-900">
            {ROUTE_TITLES[activeRoute]}
          </h1>
          <span className="hidden text-slate-300 sm:inline" aria-hidden="true">
            /
          </span>
          <span className="hidden max-w-[220px] truncate text-xs font-medium text-slate-500 sm:inline">
            {settings.workspaceName}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2 sm:gap-3">
        <div ref={searchRef} className="relative hidden w-64 md:block lg:w-80">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={globalQuery}
            onFocus={() => setSearchFocused(true)}
            onChange={(e) => {
              setGlobalQuery(e.target.value);
              setSearchFocused(true);
            }}
            placeholder="Search invoice no., supplier, GSTIN..."
            aria-label="Global workspace search"
            className="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 pl-9 pr-3 text-xs text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/15"
          />

          {searchFocused && trimmed.length > 0 && (
            <div className="absolute right-0 top-full mt-2 w-96 rounded-xl border border-slate-200 bg-white p-2 shadow-lg">
              {matchedInvoices.length === 0 && matchedSuppliers.length === 0 ? (
                <p className="px-3 py-4 text-center text-xs text-slate-500">
                  No matching sample invoices or suppliers for &ldquo;{globalQuery}&rdquo;.
                </p>
              ) : (
                <div className="space-y-2">
                  {matchedInvoices.length > 0 && (
                    <div>
                      <p className="px-2 py-1 text-[11px] font-semibold text-slate-400">
                        Invoices
                      </p>
                      {matchedInvoices.map((inv) => (
                        <button
                          key={inv.id}
                          type="button"
                          onClick={() => {
                            selectInvoiceForReview(inv.id);
                            setGlobalQuery('');
                            setSearchFocused(false);
                          }}
                          className="flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-xs hover:bg-slate-50"
                        >
                          <div className="min-w-0">
                            <p className="font-mono font-semibold text-slate-900">
                              {inv.invoiceNumber}
                            </p>
                            <p className="truncate text-slate-500">{inv.supplierName}</p>
                          </div>
                          <span className="ml-3 shrink-0 font-mono font-medium text-slate-700 tabular-nums">
                            {formatINR(inv.totalAmount)}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}

                  {matchedSuppliers.length > 0 && (
                    <div>
                      <p className="px-2 py-1 text-[11px] font-semibold text-slate-400">
                        Suppliers
                      </p>
                      {matchedSuppliers.map((sup) => (
                        <button
                          key={sup.id}
                          type="button"
                          onClick={() => {
                            navigate('invoices', { supplierFilterId: sup.id });
                            setGlobalQuery('');
                            setSearchFocused(false);
                          }}
                          className="flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-xs hover:bg-slate-50"
                        >
                          <div className="min-w-0">
                            <p className="truncate font-medium text-slate-900">
                              {sup.name}
                            </p>
                            <p className="font-mono text-[11px] text-slate-500">
                              {sup.gstin}
                            </p>
                          </div>
                          <span className="ml-2 shrink-0 text-[11px] font-medium text-indigo-600">
                            View bills
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        <div ref={notifRef} className="relative">
          <button
            type="button"
            onClick={() => setNotifOpen((o) => !o)}
            className="relative flex h-10 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 text-slate-600 hover:bg-slate-50"
            aria-label={`Notifications, ${unreadCount} unread`}
          >
            <Bell className="h-4 w-4" />
            {unreadCount > 0 && (
              <span className="font-mono text-xs font-semibold text-rose-600 tabular-nums">
                {unreadCount}
              </span>
            )}
          </button>

          {notifOpen && (
            <div className="absolute right-0 top-full mt-2 w-80 rounded-xl border border-slate-200 bg-white shadow-lg sm:w-96">
              <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
                <span className="text-xs font-semibold text-slate-900">
                  Review Notifications ({unreadCount} unread)
                </span>
                {unreadCount > 0 && (
                  <button
                    type="button"
                    onClick={markAllNotificationsRead}
                    className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-700"
                  >
                    <Check className="h-3 w-3" />
                    Mark all read
                  </button>
                )}
              </div>
              <div className="max-h-80 divide-y divide-slate-100 overflow-y-auto">
                {notifications.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      markNotificationRead(item.id);
                      navigate(item.targetRoute, {
                        invoiceId: item.targetInvoiceId,
                      });
                      setNotifOpen(false);
                    }}
                    className={`block w-full px-4 py-3 text-left transition-colors hover:bg-slate-50 ${
                      item.read ? 'opacity-70' : 'bg-indigo-50/30'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-semibold text-slate-900">
                        {item.title}
                      </span>
                      <span className="text-[11px] text-slate-400">
                        {item.timeLabel}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-slate-600">{item.detail}</p>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2.5 border-l border-slate-200 pl-2 sm:pl-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-900 text-xs font-semibold text-white">
            AD
          </div>
          <div className="hidden text-left sm:block">
            <p className="text-xs font-semibold leading-tight text-slate-900 whitespace-nowrap">
              CA Ananya Deshmukh
            </p>
            <p className="text-[11px] leading-tight text-slate-500 whitespace-nowrap">
              Partner · Reviewer
            </p>
          </div>
        </div>
      </div>
    </header>
  );
}
