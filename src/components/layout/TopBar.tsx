import { Bell, Check, LogOut, Menu, Search, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { formatINR } from '../../services/formatters';
import { useWorkspace } from '../../state/WorkspaceContext';
import type { AppRoute, WorkspaceRole } from '../../types/domain';

const ROUTE_TITLES: Record<AppRoute, string> = {
  dashboard: 'Dashboard',
  invoices: 'Invoices',
  review: 'Review Centre',
  suppliers: 'Suppliers',
  reports: 'Reports',
  settings: 'Settings',
};

const ROLE_LABELS: Record<WorkspaceRole, string> = {
  WORKSPACE_ADMIN: 'Workspace Admin',
  REVIEWER: 'Reviewer',
  UPLOADER: 'Uploader',
  VIEWER: 'Viewer',
};

function getInitials(fullName: string): string {
  const parts = fullName.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return 'NB';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

export function TopBar({ onOpenMobileNav }: { onOpenMobileNav: () => void }) {
  const {
    activeRoute,
    currentUser,
    workspaces,
    activeWorkspaceId,
    activeWorkspace,
    activeWorkspaceRole,
    switchWorkspace,
    logout,
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
  const [mobileSearchOpen, setMobileSearchOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);
  const mobileSearchRef = useRef<HTMLDivElement>(null);
  const mobileInputRef = useRef<HTMLInputElement>(null);
  const mobileTriggerRef = useRef<HTMLButtonElement>(null);
  const notifRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (searchRef.current && !searchRef.current.contains(target)) {
        setSearchFocused(false);
      }
      if (
        mobileSearchRef.current &&
        !mobileSearchRef.current.contains(target)
      ) {
        setMobileSearchOpen(false);
      }
      if (notifRef.current && !notifRef.current.contains(target)) {
        setNotifOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setSearchFocused(false);
        setNotifOpen(false);
        if (mobileSearchOpen) {
          setMobileSearchOpen(false);
          mobileTriggerRef.current?.focus();
        }
      }
    };

    document.addEventListener('mousedown', handleOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [mobileSearchOpen]);

  useEffect(() => {
    if (mobileSearchOpen) {
      mobileInputRef.current?.focus();
    }
  }, [mobileSearchOpen]);

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
          `${sup.name} ${sup.gstin} ${sup.category}`
            .toLowerCase()
            .includes(trimmed)
        )
        .slice(0, 3)
    : [];

  const workspaceLabel = activeWorkspace?.name ?? settings.workspaceName;
  const userName = currentUser?.fullName ?? 'Authenticated User';
  const roleLabel = activeWorkspaceRole
    ? ROLE_LABELS[activeWorkspaceRole]
    : 'Member';

  const renderSearchResults = (dropdownClassName: string) => (
    <div
      className={dropdownClassName}
      role="region"
      aria-label="Search results"
    >
      {matchedInvoices.length === 0 && matchedSuppliers.length === 0 ? (
        <p className="px-3 py-4 text-center text-xs text-slate-500">
          No matching invoices or suppliers for &ldquo;{globalQuery}&rdquo;.
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
                    setMobileSearchOpen(false);
                  }}
                  className="flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-xs hover:bg-slate-50"
                >
                  <div className="min-w-0">
                    <p className="font-mono font-semibold text-slate-900">
                      {inv.invoiceNumber}
                    </p>
                    <p className="truncate text-slate-500">
                      {inv.supplierName}
                    </p>
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
                    setMobileSearchOpen(false);
                  }}
                  className="flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-xs hover:bg-slate-50"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium text-slate-900">
                      {sup.name}
                    </p>
                    <p className="font-mono text-[11px] text-slate-500">
                      {sup.gstin || 'No GSTIN'}
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
  );

  return (
    <header className="sticky top-0 z-30 shrink-0 border-b border-slate-200 bg-white">
      <div className="flex h-16 items-center justify-between gap-3 px-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={onOpenMobileNav}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 lg:hidden"
            aria-label="Open navigation menu"
          >
            <Menu className="h-4 w-4" />
          </button>

          <div className="flex min-w-0 items-center gap-2 text-sm">
            <h1 className="truncate font-semibold text-slate-900">
              {ROUTE_TITLES[activeRoute]}
            </h1>
            <span
              className="hidden text-slate-300 sm:inline"
              aria-hidden="true"
            >
              /
            </span>
            {workspaces.length > 1 ? (
              <select
                aria-label="Active workspace"
                value={activeWorkspaceId ?? ''}
                onChange={(e) => switchWorkspace(e.target.value)}
                className="hidden h-8 max-w-[220px] rounded-md border border-slate-200 bg-slate-50 px-2 text-xs font-medium text-slate-700 focus:border-indigo-500 focus:bg-white focus:outline-none sm:inline-block"
              >
                {workspaces.map((ws) => (
                  <option key={ws.workspaceId} value={ws.workspaceId}>
                    {ws.name} ({ws.workspaceCode})
                  </option>
                ))}
              </select>
            ) : (
              <span className="hidden max-w-[220px] truncate text-xs font-medium text-slate-500 sm:inline">
                {workspaceLabel}
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 sm:gap-3">
          <button
            ref={mobileTriggerRef}
            type="button"
            onClick={() => {
              setNotifOpen(false);
              setMobileSearchOpen((open) => !open);
            }}
            aria-label={
              mobileSearchOpen
                ? 'Close workspace search'
                : 'Open workspace search'
            }
            aria-expanded={mobileSearchOpen}
            className="flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 md:hidden"
          >
            {mobileSearchOpen ? (
              <X className="h-4 w-4" />
            ) : (
              <Search className="h-4 w-4" />
            )}
          </button>

          <div ref={searchRef} className="relative hidden w-60 md:block lg:w-72">
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

            {searchFocused &&
              trimmed.length > 0 &&
              renderSearchResults(
                'absolute right-0 top-full mt-2 w-96 rounded-xl border border-slate-200 bg-white p-2 shadow-lg'
              )}
          </div>

          <div ref={notifRef} className="relative">
            <button
              type="button"
              onClick={() => {
                setMobileSearchOpen(false);
                setNotifOpen((o) => !o);
              }}
              className="relative flex h-10 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 text-slate-600 hover:bg-slate-50"
              aria-label={`Notifications, ${unreadCount} unread`}
              aria-expanded={notifOpen}
            >
              <Bell className="h-4 w-4" />
              {unreadCount > 0 && (
                <span className="font-mono text-xs font-semibold text-rose-600 tabular-nums">
                  {unreadCount}
                </span>
              )}
            </button>

            {notifOpen && (
              <div className="absolute right-0 top-full mt-2 w-[min(22rem,calc(100vw-1.5rem))] rounded-xl border border-slate-200 bg-white shadow-lg sm:w-96">
                <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
                  <span className="text-xs font-semibold text-slate-900">
                    Review Alerts ({unreadCount} unread)
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
                  {notifications.length === 0 ? (
                    <p className="px-4 py-6 text-center text-xs text-slate-500">
                      No active alerts for your current workspace settings.
                    </p>
                  ) : (
                    notifications.map((item) => (
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
                        <p className="mt-1 text-xs text-slate-600">
                          {item.detail}
                        </p>
                      </button>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

          <div className="flex items-center gap-2 border-l border-slate-200 pl-2 sm:pl-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-900 text-xs font-semibold text-white">
              {getInitials(userName)}
            </div>
            <div className="hidden text-left sm:block">
              <p className="max-w-[140px] truncate text-xs font-semibold leading-tight text-slate-900">
                {userName}
              </p>
              <p className="text-[11px] leading-tight text-slate-500 whitespace-nowrap">
                {roleLabel}
              </p>
            </div>
            <button
              type="button"
              onClick={() => void logout()}
              title="Sign out"
              aria-label="Sign out"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50 hover:text-slate-900"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      {mobileSearchOpen && (
        <div
          ref={mobileSearchRef}
          className="border-t border-slate-100 bg-white px-4 py-3 md:hidden"
        >
          {workspaces.length > 1 && (
            <div className="mb-2.5">
              <select
                aria-label="Switch workspace"
                value={activeWorkspaceId ?? ''}
                onChange={(e) => switchWorkspace(e.target.value)}
                className="h-9 w-full rounded-lg border border-slate-200 bg-slate-50 px-2.5 text-xs font-medium text-slate-800"
              >
                {workspaces.map((ws) => (
                  <option key={ws.workspaceId} value={ws.workspaceId}>
                    {ws.name} ({ws.workspaceCode})
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                ref={mobileInputRef}
                type="text"
                value={globalQuery}
                onChange={(e) => setGlobalQuery(e.target.value)}
                placeholder="Search invoice no., supplier, GSTIN..."
                aria-label="Mobile workspace search"
                className="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 pl-9 pr-3 text-xs text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/15"
              />
            </div>
            <button
              type="button"
              onClick={() => {
                setMobileSearchOpen(false);
                mobileTriggerRef.current?.focus();
              }}
              className="h-10 rounded-lg border border-slate-200 px-3 text-xs font-medium text-slate-700 hover:bg-slate-50 whitespace-nowrap"
            >
              Close
            </button>
          </div>
          {trimmed.length > 0 &&
            renderSearchResults(
              'mt-2 max-h-72 overflow-y-auto rounded-xl border border-slate-200 bg-white p-2 shadow-sm'
            )}
        </div>
      )}
    </header>
  );
}
