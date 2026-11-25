import { AlertCircle, Building2, RefreshCw } from 'lucide-react';
import { lazy, Suspense } from 'react';
import { AuthScreen } from './components/auth/AuthScreen';
import { AppShell } from './components/layout/AppShell';
import { WorkspaceProvider, useWorkspace } from './state/WorkspaceContext';

const DashboardPage = lazy(() =>
  import('./pages/DashboardPage').then((m) => ({ default: m.DashboardPage }))
);
const InvoicesPage = lazy(() =>
  import('./pages/InvoicesPage').then((m) => ({ default: m.InvoicesPage }))
);
const ReviewCentrePage = lazy(() =>
  import('./pages/ReviewCentrePage').then((m) => ({
    default: m.ReviewCentrePage,
  }))
);
const SuppliersPage = lazy(() =>
  import('./pages/SuppliersPage').then((m) => ({ default: m.SuppliersPage }))
);
const ReportsPage = lazy(() =>
  import('./pages/ReportsPage').then((m) => ({ default: m.ReportsPage }))
);
const SettingsPage = lazy(() =>
  import('./pages/SettingsPage').then((m) => ({ default: m.SettingsPage }))
);

function RouteLoadingFallback() {
  return (
    <div
      role="status"
      aria-live="polite"
      className="space-y-4 rounded-xl border border-slate-200 bg-white p-6"
    >
      <div className="h-5 w-48 animate-pulse rounded bg-slate-200" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="h-24 animate-pulse rounded-lg bg-slate-100" />
        <div className="h-24 animate-pulse rounded-lg bg-slate-100" />
        <div className="h-24 animate-pulse rounded-lg bg-slate-100" />
        <div className="h-24 animate-pulse rounded-lg bg-slate-100" />
      </div>
      <span className="sr-only">Loading workspace view...</span>
    </div>
  );
}

function WorkspaceRouter() {
  const { activeRoute } = useWorkspace();

  switch (activeRoute) {
    case 'dashboard':
      return <DashboardPage />;
    case 'invoices':
      return <InvoicesPage />;
    case 'review':
      return <ReviewCentrePage />;
    case 'suppliers':
      return <SuppliersPage />;
    case 'reports':
      return <ReportsPage />;
    case 'settings':
      return <SettingsPage />;
    default:
      return <DashboardPage />;
  }
}

function AuthenticatedApp() {
  const {
    isDemoMode,
    authStatus,
    workspaces,
    activeWorkspaceId,
    workspaceError,
    refreshWorkspace,
    logout,
  } = useWorkspace();

  if (!isDemoMode && authStatus === 'checking') {
    return (
      <div
        role="status"
        aria-live="polite"
        className="flex min-h-screen items-center justify-center bg-slate-50 px-4"
      >
        <div className="flex flex-col items-center gap-3 rounded-xl border border-slate-200 bg-white px-8 py-6 text-center shadow-xs">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
          <p className="text-sm font-medium text-slate-700">
            Verifying NORUS BILLWISE session...
          </p>
        </div>
      </div>
    );
  }

  if (!isDemoMode && authStatus === 'unauthenticated') {
    return <AuthScreen />;
  }

  if (workspaces.length === 0 || !activeWorkspaceId) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
        <div className="max-w-md rounded-xl border border-slate-200 bg-white p-6 text-center shadow-xs">
          <Building2 className="mx-auto h-10 w-10 text-slate-400" />
          <h1 className="mt-3 text-base font-semibold text-slate-900">
            No Workspace Membership Found
          </h1>
          <p className="mt-1.5 text-xs leading-relaxed text-slate-500">
            Your account does not currently belong to any active client
            workspace. Contact your organization administrator or sign out to
            switch accounts.
          </p>
          <button
            type="button"
            onClick={() => void logout()}
            className="mt-4 inline-flex h-9 items-center justify-center rounded-lg border border-slate-300 bg-white px-4 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            Sign Out
          </button>
        </div>
      </div>
    );
  }

  return (
    <AppShell>
      {workspaceError && (
        <div
          role="alert"
          className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs text-rose-900"
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0 text-rose-600" />
            <span>{workspaceError}</span>
          </div>
          <button
            type="button"
            onClick={() => void refreshWorkspace()}
            className="inline-flex items-center gap-1.5 rounded-lg border border-rose-300 bg-white px-2.5 py-1 text-xs font-medium text-rose-800 hover:bg-rose-100"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Retry
          </button>
        </div>
      )}
      <Suspense fallback={<RouteLoadingFallback />}>
        <WorkspaceRouter />
      </Suspense>
    </AppShell>
  );
}

export default function App() {
  return (
    <WorkspaceProvider>
      <AuthenticatedApp />
    </WorkspaceProvider>
  );
}
