import {
  BarChart3,
  Building2,
  FileCheck2,
  FileText,
  LayoutDashboard,
  Settings,
  ShieldCheck,
  X,
} from 'lucide-react';
import { useEffect } from 'react';
import { useWorkspace } from '../../state/WorkspaceContext';
import type { AppRoute } from '../../types/domain';
import { Logo } from '../common/Logo';

interface NavItem {
  route: AppRoute;
  label: string;
  icon: typeof LayoutDashboard;
}

const NAV_ITEMS: NavItem[] = [
  { route: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { route: 'invoices', label: 'Invoices', icon: FileText },
  { route: 'review', label: 'Review Centre', icon: FileCheck2 },
  { route: 'suppliers', label: 'Suppliers', icon: Building2 },
  { route: 'reports', label: 'Reports', icon: BarChart3 },
  { route: 'settings', label: 'Settings', icon: Settings },
];

export function Sidebar({
  mobileOpen,
  onCloseMobile,
}: {
  mobileOpen: boolean;
  onCloseMobile: () => void;
}) {
  const { activeRoute, navigate, invoices, reportSummary } = useWorkspace();

  useEffect(() => {
    if (!mobileOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCloseMobile();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [mobileOpen, onCloseMobile]);

  const pendingOrFlaggedCount =
    reportSummary?.outstandingReviewCount ??
    invoices.filter(
      (inv) => inv.status === 'Pending Review' || inv.status === 'Flagged'
    ).length;

  const handleSelect = (route: AppRoute) => {
    navigate(route);
    onCloseMobile();
  };

  const sidebarContent = (
    <div className="flex h-full flex-col bg-slate-950 text-slate-200">
      <div className="flex items-center justify-between border-b border-slate-800/80 px-5 py-4">
        <Logo />
        <button
          type="button"
          onClick={onCloseMobile}
          className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-white lg:hidden"
          aria-label="Close navigation menu"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      <div className="px-3 py-5">
        <p className="px-3 pb-2 text-xs font-medium text-slate-400">
          Workspace Navigation
        </p>
        <nav className="space-y-1" aria-label="Main navigation">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = activeRoute === item.route;
            return (
              <button
                key={item.route}
                type="button"
                onClick={() => handleSelect(item.route)}
                className={`flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-sm font-medium whitespace-nowrap transition-colors duration-150 ${
                  isActive
                    ? 'bg-indigo-600 text-white'
                    : 'text-slate-300 hover:bg-slate-900 hover:text-white'
                }`}
              >
                <span className="flex items-center gap-3">
                  <Icon className="h-4 w-4 shrink-0" />
                  <span>{item.label}</span>
                </span>
                {item.route === 'review' && pendingOrFlaggedCount > 0 && (
                  <span
                    className={`font-mono text-xs font-semibold tabular-nums ${
                      isActive ? 'text-indigo-100' : 'text-amber-300'
                    }`}
                  >
                    {pendingOrFlaggedCount}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      <div className="mt-auto border-t border-slate-800/80 p-4">
        <div className="rounded-lg border border-slate-800 bg-slate-900/80 p-3">
          <div className="flex items-center gap-2 text-xs font-medium text-slate-200">
            <ShieldCheck className="h-4 w-4 shrink-0 text-emerald-400" />
            <span>Human Review Enforced</span>
          </div>
          <p className="mt-1.5 text-[11px] leading-relaxed text-slate-400">
            Explicit reviewer approval is required before any invoice is
            marked Verified.
          </p>
        </div>
        <div className="mt-3 flex items-center justify-between px-1 text-[11px] text-slate-400">
          <span>NORUS AI</span>
          <span>India GST Edition</span>
        </div>
      </div>
    </div>
  );

  return (
    <>
      <aside className="hidden w-64 shrink-0 border-r border-slate-200 lg:block">
        {sidebarContent}
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <div
            className="fixed inset-0 bg-slate-950/60"
            onClick={onCloseMobile}
            aria-hidden="true"
          />
          <aside className="relative z-10 w-64 max-w-[85vw] shadow-2xl">
            {sidebarContent}
          </aside>
        </div>
      )}
    </>
  );
}
